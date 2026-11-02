"""Sofdec(SFD) 동영상의 영상 스트림만 갈아 끼운다.

이 게임의 SFD 는 매우 규칙적이다.

* 파일 전체가 **2048바이트 섹터**로 나뉘고, 섹터마다 MPEG-1 팩 헤더가 하나씩.
* 섹터 하나에는 스트림 하나만 들어간다.
  - 영상(0xE0): PES 길이 2030, 페이로드 정확히 **2018바이트**
  - 음성(0xC0): PES 길이 2023 + 패딩(0xBE), ADX 데이터
  - 그 밖에 시스템 헤더(0xBB), Sofdec 메타(0xBF)
* 영상 PES 는 그 섹터 안에서 **새 픽처가 시작될 때만** 타임스탬프를 싣는다.
  참조 프레임(I/P)은 PTS+DTS, B 프레임은 PTS 만. 남는 자리는 0xFF 로 채워
  PES 길이를 2030 으로 맞춘다 (스터핑 0 / 5 / 9 바이트).

ffmpeg 는 이 컨테이너를 **읽지만 쓰지는 못한다** (ADX 를 MPEG-PS 로 mux 하지
못한다).  그래서 원본 섹터 배치를 그대로 두고 영상 페이로드만 새로 채운다.
음성·헤더 섹터와 모든 팩 헤더(SCR)는 원본 바이트 그대로라, 재생 타이밍과
버퍼 모델이 원본과 같게 유지된다.

전제는 프레임 수가 같은 것뿐이다.  타임스탬프는 원본에서 '표시 순서별 PTS'
표를 뽑아 새 영상의 프레임 배치에 맞춰 다시 계산하므로, 인코더가 B 프레임을
원본과 다르게 놓아도 상관없다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


SECTOR = 2048
VIDEO_PES_LEN = 2030
VIDEO_PAYLOAD = 2018
PACK_HEADER = 12
PICTURE_START = b"\x00\x00\x01\x00"
SEQUENCE_END = b"\x00\x00\x01\xb7"


@dataclass
class VideoSector:
    index: int
    kind: int          # 0=없음 1=PTS 2=PTS+DTS
    pts: int | None
    dts: int | None
    payload_length: int


def _timestamp(raw: bytes) -> int:
    return (
        ((raw[0] >> 1) & 7) << 30
        | raw[1] << 22
        | ((raw[2] >> 1) & 0x7F) << 15
        | raw[3] << 7
        | (raw[4] >> 1)
    )


def _encode_timestamp(value: int, marker: int) -> bytes:
    return bytes(
        (
            (marker << 4) | (((value >> 30) & 7) << 1) | 1,
            (value >> 22) & 0xFF,
            (((value >> 15) & 0x7F) << 1) | 1,
            (value >> 7) & 0xFF,
            ((value & 0x7F) << 1) | 1,
        )
    )


def analyse(sfd: bytes) -> tuple[list[VideoSector], bytearray, list[int]]:
    """원본에서 영상 섹터 목록, 영상 스트림, 픽처 시작 위치를 뽑는다."""

    sectors: list[VideoSector] = []
    stream = bytearray()
    for index in range(len(sfd) // SECTOR):
        base = index * SECTOR
        if sfd[base : base + 4] != b"\x00\x00\x01\xba":
            continue
        cursor = base + PACK_HEADER
        if sfd[cursor : cursor + 3] != b"\x00\x00\x01" or sfd[cursor + 3] != 0xE0:
            continue
        length = int.from_bytes(sfd[cursor + 4 : cursor + 6], "big")
        end = cursor + 6 + length
        probe = cursor + 6
        while sfd[probe] == 0xFF:
            probe += 1
        probe += 2  # MPEG-1 STD buffer field
        flag = sfd[probe]
        if flag == 0x0F:
            kind, pts, dts = 0, None, None
            probe += 1
        elif flag >> 4 == 2:
            kind, pts, dts = 1, _timestamp(sfd[probe : probe + 5]), None
            probe += 5
        elif flag >> 4 == 3:
            kind = 2
            pts = _timestamp(sfd[probe : probe + 5])
            dts = _timestamp(sfd[probe + 5 : probe + 10])
            probe += 10
        else:
            raise ValueError(f"섹터 {index}: 알 수 없는 PES 플래그 {flag:#x}")
        sectors.append(VideoSector(index, kind, pts, dts, end - probe))
        stream += sfd[probe:end]
    return sectors, stream, _picture_offsets(stream)


def _picture_offsets(stream: bytes) -> list[int]:
    offsets: list[int] = []
    position = 0
    while True:
        found = stream.find(PICTURE_START, position)
        if found < 0:
            return offsets
        offsets.append(found)
        position = found + 4


def _is_reference(stream: bytes, offset: int) -> bool:
    """픽처 부호화 유형: 1=I 2=P 3=B.  I/P 는 참조 프레임."""

    return ((stream[offset + 5] >> 3) & 7) in (1, 2)


SEQUENCE_START = b"\x00\x00\x01\xb3"


def display_order(references: list[bool]) -> list[int]:
    """복호 순서 -> 표시 순서 번호.

    참조 프레임(I/P)은 뒤따르는 B 프레임보다 먼저 복호되지만 나중에 표시된다.
    IPBBPBB 는 표시 순서로 I(0) B(1) B(2) P(3) B(4) B(5) P(6) 이 된다.
    """

    index = [0] * len(references)
    held: int | None = None
    slot = 0
    for order, reference in enumerate(references):
        if reference:
            if held is not None:
                index[held] = slot
                slot += 1
            held = order
        else:
            index[order] = slot
            slot += 1
    if held is not None:
        index[held] = slot
    return index


def sequence_size(stream: bytes) -> tuple[int, int]:
    """시퀀스 헤더의 가로x세로.  동영상마다 다를 수 있다 (MOVEB_26 은 160x240)."""

    index = stream.find(SEQUENCE_START)
    if index < 0:
        raise ValueError("시퀀스 헤더가 없습니다")
    raw = stream[index + 4 : index + 7]
    return (raw[0] << 4) | (raw[1] >> 4), ((raw[1] & 0x0F) << 8) | raw[2]


def sequence_rate(stream: bytes) -> tuple[int, int]:
    """시퀀스 헤더의 bit_rate_value 와 vbv_buffer_size 를 읽는다."""

    index = stream.find(SEQUENCE_START)
    if index < 0:
        raise ValueError("시퀀스 헤더가 없습니다")
    raw = stream[index + 4 : index + 12]
    bit_rate = (raw[4] << 10) | (raw[5] << 2) | (raw[6] >> 6)
    vbv = ((raw[6] & 0x1F) << 5) | (raw[7] >> 3)
    return bit_rate, vbv


def apply_sequence_rate(stream: bytes, bit_rate: int, vbv: int) -> bytes:
    """모든 시퀀스 헤더의 비트레이트/VBV 값을 원본 것으로 맞춘다.

    PS2 쪽 재생기는 이 값으로 입력 버퍼를 잡는 것으로 보이므로, 실제 전달
    일정을 원본에 맞추는 것과 함께 선언 값도 원본과 같게 둔다.  양자화 행렬
    적재 플래그(마지막 3비트)는 우리 인코딩의 것을 그대로 남긴다.
    """

    output = bytearray(stream)
    position = 0
    count = 0
    while True:
        index = output.find(SEQUENCE_START, position)
        if index < 0:
            break
        base = index + 4
        tail = output[base + 7] & 7
        output[base + 4] = (bit_rate >> 10) & 0xFF
        output[base + 5] = (bit_rate >> 2) & 0xFF
        output[base + 6] = ((bit_rate & 3) << 6) | (1 << 5) | ((vbv >> 5) & 0x1F)
        output[base + 7] = ((vbv & 0x1F) << 3) | tail
        position = index + 4
        count += 1
    if count == 0:
        raise ValueError("시퀀스 헤더를 찾지 못했습니다")
    return bytes(output)


def align_to_original(video: bytes, original_stream: bytes, capacity: int) -> bytes:
    """새 영상의 각 픽처를 원본 픽처와 같은 바이트 위치에서 시작하게 한다.

    섹터 배치를 그대로 두고 크기만 작은 스트림을 넣으면, 데이터가 원본보다
    **일찍** 도착해 재생기의 영상 입력 버퍼가 넘친다.  (실제로 그렇게 만든
    첫 판은 3초쯤부터 원본 VBV 192KB 를 넘어서다가 화면이 멈췄다.)

    그래서 픽처 앞을 0x00 으로 메워 원본과 같은 시점에 도착하게 한다.
    MPEG-2 는 시작 코드 앞의 0 바이트를 스터핑으로 건너뛰므로 안전하다.
    우리 픽처가 원본보다 큰 경우에는 밀리는데, 그만큼은 뒤 픽처의 여유가
    흡수한다.
    """

    new_pics = _picture_offsets(video)
    old_pics = _picture_offsets(original_stream)
    if len(new_pics) != len(old_pics):
        raise ValueError(f"프레임 수가 다릅니다: {len(new_pics)} != {len(old_pics)}")

    bounds = new_pics + [len(video)]
    sizes = [bounds[i + 1] - bounds[i] for i in range(len(new_pics))]
    # 뒤에 남은 픽처들이 들어갈 자리는 반드시 비워 둬야 하므로, 그만큼은
    # 앞당겨 채운다.  덕분에 꼬리 몇 장만 원본보다 일찍 도착하고, 재생이
    # 끝나가는 구간이라 버퍼에 부담이 없다.
    remaining = [0] * (len(sizes) + 1)
    for i in range(len(sizes) - 1, -1, -1):
        remaining[i] = remaining[i + 1] + sizes[i]

    output = bytearray(video[: new_pics[0]])   # 시퀀스 헤더 등 앞부분
    for order, start in enumerate(new_pics):
        target = min(old_pics[order], capacity - remaining[order])
        if len(output) < target:
            output += b"\x00" * (target - len(output))
        output += video[start : bounds[order + 1]]
    if len(output) > capacity:
        raise ValueError(
            f"정렬 후 {len(output)} 바이트로 용량 {capacity} 를 넘습니다. 비트레이트를 낮추세요."
        )
    return bytes(output)



def _stamped_pictures(sectors: list[VideoSector], pictures: list[int]) -> list[tuple[int, VideoSector]]:
    """타임스탬프를 실은 섹터를 픽처(복호 순서)에 짝지어 준다.

    PES 의 타임스탬프는 '그 패킷에서 시작하는 첫 액세스 유닛'의 것이다.  액세스
    유닛은 픽처 시작 코드가 아니라 그 앞의 시퀀스/GOP 헤더에서 시작하므로,
    스탬프를 실은 섹터에 픽처 시작 코드가 아예 없을 수도 있다.  그래서 '섹터
    시작 이후 처음 나오는, 아직 안 쓰인 픽처'로 짝을 짓는다.

    반대로 한 섹터에서 픽처가 둘 시작하면 스탬프는 앞의 것 하나뿐이라 스탬프
    수가 픽처 수보다 적을 수 있다 (PLO_03: 1157 < 1205).  모자란 자리는
    _fill_gaps 가 메운다.
    """

    pairs: list[tuple[int, VideoSector]] = []
    cursor = 0
    for position, sector in enumerate(sectors):
        if sector.kind == 0:
            continue
        start = position * VIDEO_PAYLOAD
        while cursor < len(pictures) and pictures[cursor] < start:
            cursor += 1
        if cursor >= len(pictures):
            break
        pairs.append((cursor, sector))
        cursor += 1
    return pairs


def _fill_gaps(table: list[int | None]) -> list[int]:
    """스탬프가 없던 자리를 양옆 값 사이를 보간해 메운다.

    원본의 틱 간격은 3006 근처에서 조금씩 흔들려서 (2916 이나 3007 도 나온다)
    고정 간격으로 계산하지 않고 아는 값 사이를 나눠 쓴다.
    """

    known = [index for index, value in enumerate(table) if value is not None]
    if not known:
        raise ValueError("타임스탬프가 하나도 없습니다")
    if len(known) == 1:
        return [table[known[0]]] * len(table)

    filled: list[float | None] = list(table)
    step = (table[known[-1]] - table[known[0]]) / (known[-1] - known[0])
    for index in range(len(table)):
        if filled[index] is not None:
            continue
        before = next((k for k in reversed(known) if k < index), None)
        after = next((k for k in known if k > index), None)
        if before is not None and after is not None:
            share = (index - before) / (after - before)
            value = table[before] + (table[after] - table[before]) * share
        elif before is not None:
            value = table[before] + step * (index - before)
        else:
            value = table[after] - step * (after - index)
        filled[index] = value
    return [max(0, round(value)) for value in filled]


def _display_pts_table(sectors: list[VideoSector], stream: bytes, pictures: list[int]) -> list[int]:
    """원본에서 '표시 순서 n 번째 프레임의 PTS' 표를 만든다.

    ``DTS = 표[복호 순서]``, ``PTS = 표[표시 순서]`` 라는 관계가 원본에서 그대로
    성립한다 (원본 앞부분: 복호 1번 P 의 DTS 3006 = 표[1], PTS 9018 = 표[3]).
    틱 간격이 일정하지 않아도 되므로 계산식으로 만드는 것보다 안전하다.
    """

    order = display_order([_is_reference(stream, p) for p in pictures])
    table: list[int | None] = [None] * len(pictures)
    for decode_index, sector in _stamped_pictures(sectors, pictures):
        table[order[decode_index]] = sector.pts
    return _fill_gaps(table)


def remux(sfd: bytes, video: bytes) -> bytes:
    sectors, original_stream, original_pics = analyse(sfd)
    capacity = len(sectors) * VIDEO_PAYLOAD
    if len(video) > capacity:
        raise ValueError(f"새 영상이 큽니다: {len(video)} > {capacity}")

    new_pics = _picture_offsets(video)
    if len(new_pics) > len(original_pics):
        # 인코더가 끝에 프레임을 더 붙이는 경우가 있다 (MOVEA_20: 309 != 308).
        # 원본 길이에 맞춰 남는 뒤쪽 픽처를 잘라 낸다.
        video = video[: new_pics[len(original_pics)]]
        new_pics = new_pics[: len(original_pics)]
    if len(new_pics) != len(original_pics):
        raise ValueError(f"프레임 수가 모자랍니다: {len(new_pics)} < {len(original_pics)}")

    # 타임스탬프는 원본에서 **표시 순서별 PTS 표**를 뽑아 다시 계산한다.
    # 원본 것을 순서대로 그대로 쓰면 인코더가 B 프레임을 조금만 다르게 놓아도
    # 어긋나므로 (실제로 MOVEA_01 에서 그랬다) 배치에 의존하지 않게 한다.
    pts_by_display = _display_pts_table(sectors, original_stream, original_pics)
    new_kind = [_is_reference(video, p) for p in new_pics]
    new_display = display_order(new_kind)

    # 원본과 같은 시점에 데이터가 도착하도록 맞추고, 선언 비트레이트/VBV 도
    # 원본 값으로 되돌린다.  둘 다 하지 않으면 재생기 버퍼가 넘쳐 멈춘다.
    bit_rate, vbv = sequence_rate(original_stream)
    video = apply_sequence_rate(video, bit_rate, vbv)
    video = align_to_original(video, original_stream, capacity)
    new_pics = _picture_offsets(video)

    # 마지막 픽처 뒤에는 시퀀스 종료 코드를 두고 0x00 으로 채운다.
    padded = bytearray(video)
    if not padded.endswith(SEQUENCE_END):
        padded += SEQUENCE_END
    padded += b"\x00" * (capacity - len(padded))

    output = bytearray(sfd)
    picture_cursor = 0
    for order, sector in enumerate(sectors):
        start = order * VIDEO_PAYLOAD
        chunk = bytes(padded[start : start + VIDEO_PAYLOAD])
        # 이 섹터 안에서 새 픽처가 시작되는가
        begins = picture_cursor < len(new_pics) and start <= new_pics[picture_cursor] < start + len(chunk)
        if begins:
            reference = new_kind[picture_cursor]
            pts = pts_by_display[new_display[picture_cursor]]
            if reference:
                dts = pts_by_display[picture_cursor]
                header = _encode_timestamp(pts, 3) + _encode_timestamp(dts, 1)
                stuffing = 0
            else:
                header = _encode_timestamp(pts, 2)
                stuffing = 5
            picture_cursor += 1
            # 같은 섹터에서 시작하는 나머지 픽처는 스탬프를 싣지 않는다.
            while picture_cursor < len(new_pics) and new_pics[picture_cursor] < start + len(chunk):
                picture_cursor += 1
        else:
            header = b"\x0f"
            stuffing = 9

        body = (
            b"\xff" * stuffing
            + bytes((0x60, 0x2E))          # MPEG-1 STD 버퍼 필드 (원본과 동일)
            + header
            + chunk
        )
        if len(body) != VIDEO_PES_LEN:
            raise AssertionError(f"PES 길이 {len(body)} != {VIDEO_PES_LEN}")
        base = sector.index * SECTOR
        packet = b"\x00\x00\x01\xe0" + VIDEO_PES_LEN.to_bytes(2, "big") + body
        output[base + PACK_HEADER : base + PACK_HEADER + len(packet)] = packet

    if picture_cursor != len(new_pics):
        raise AssertionError(f"픽처 배치 실패: {picture_cursor}/{len(new_pics)}")
    if len(output) != len(sfd):
        raise AssertionError("파일 크기가 바뀌었습니다")
    return bytes(output)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="SFD 의 영상 스트림만 교체합니다.")
    parser.add_argument("original", type=Path)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    sfd = args.original.read_bytes()
    sectors, stream, pics = analyse(sfd)
    print(json.dumps({
        "영상_섹터": len(sectors),
        "영상_스트림": len(stream),
        "픽처": len(pics),
        "용량": len(sectors) * VIDEO_PAYLOAD,
    }, ensure_ascii=False))
    result = remux(sfd, args.video.read_bytes())
    args.output.write_bytes(result)
    print(json.dumps({"output": str(args.output), "bytes": len(result)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
