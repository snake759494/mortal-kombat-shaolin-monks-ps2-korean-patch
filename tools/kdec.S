/* 한글 2바이트 글자 디코더 (원래 0x37fb90 / 0x37fc30 대체)
 *
 * 입력: a0 = char** (읽은 만큼 전진), a1 = 폰트 객체(호출부 지연 슬롯에서 넣음)
 * 출력: v0 = 글리프 번호(0xff = 그리지 않음)
 *
 * 한글은 리드(A1-FE)+트레일(A1-FE) 두 바이트, 번호 k = (리드-A1)*94 + (트레일-A1).
 * 글리프 슬롯 0xF0~0xFE 를 돌려 쓰며, 슬롯의 UV(+0x6efc)·폭(+0x7ef4, +0x82f0)·
 * 번호 k 는 kslot() 이 캐시 칸으로 바꾸고, 배치 표로 칸의 UV 를 계산한다.
 * 정적 행 표(바이트1=폭, 바이트3=세로 보정)를 그 자리에서 채운다.
 * 원래 1바이트 동작(소문자 접기, 0/공백→0xff, 맵 표 조회)은 그대로 둔다.
 * 1바이트 글자는 잎 함수처럼 t 레지스터만 쓴다.
 */
    .set noreorder
    .set noat
    .set hardfloat
    .text
    .globl kdec_small
    .globl kdec_big
    .globl kpeek_small
    .globl kpeek_big

/* 커닝용 다음 글자 미리읽기: 엔진은 (주 포인터 + 1) 을 a0 = &주포인터 + 4 에 넣어 부른다.
 * 주 디코드가 이미 포인터를 전진시켰으므로 그 값으로 바꿔 읽고, 한글이면 0xff(커닝 없음). */
kpeek_small:
    lw $t0, -4($a0)
    sw $t0, 0($a0)
    lbu $v1, 0($t0)
    sltiu $t1, $v1, 0xa1
    bnez $t1, kdec_small
    lbu $t2, 1($t0)
    sltiu $t1, $t2, 0xa1
    bnez $t1, kdec_small
    nop
    jr $ra
    addiu $v0, $zero, 0xff

kpeek_big:
    lw $t0, -4($a0)
    sw $t0, 0($a0)
    lbu $v1, 0($t0)
    sltiu $t1, $v1, 0xa1
    bnez $t1, kdec_big
    lbu $t2, 1($t0)
    sltiu $t1, $t2, 0xa1
    bnez $t1, kdec_big
    nop
    jr $ra
    addiu $v0, $zero, 0xff

kdec_small:                     /* 폰트 플래그 2 없음: 맵 0x52d540, 소문자 접기 */
    lui $t9, 0x53
    addiu $t9, $t9, -0x2ac0
    b common
    addiu $t8, $zero, 1

kdec_big:                       /* 폰트 플래그 2: 맵 0x52d640 */
    lui $t9, 0x53
    addiu $t9, $t9, -0x29c0
    addiu $t8, $zero, 0

common:
    beqz $a0, ret_ff
    nop
    lw $t0, 0($a0)
    beqz $t0, ret_ff
    nop
    lbu $v1, 0($t0)
    sltiu $t1, $v1, 0xa1
    bnez $t1, single
    lbu $t2, 1($t0)
    sltiu $t1, $t2, 0xa1
    bnez $t1, single
    nop

    /* ---- 한글 ---- */
    addiu $v1, $v1, -0xa1
    sll $t1, $v1, 6             /* *64 */
    sll $t3, $v1, 5             /* *32 */
    addu $t1, $t1, $t3
    sll $t3, $v1, 1             /* *2 : 96 - 2 = 94 */
    subu $t1, $t1, $t3
    addiu $t2, $t2, -0xa1
    addu $t3, $t1, $t2          /* t3 = k */
    addiu $t0, $t0, 2
    sw $t0, 0($a0)

    /* k → 캐시 칸 (kcache.c). s0-s7, fp 는 128비트로 보존(sq), C 는 32비트만 저장하므로 */
    addiu $sp, $sp, -0xc0
    .word 0x7fb00000            /* sq s0, 0x00(sp) */
    .word 0x7fb10010            /* sq s1, 0x10(sp) */
    .word 0x7fb20020
    .word 0x7fb30030
    .word 0x7fb40040
    .word 0x7fb50050
    .word 0x7fb60060
    .word 0x7fb70070
    .word 0x7fbe0080            /* sq fp */
    sw $ra, 0x90($sp)
    sw $a1, 0x94($sp)
    move $a0, $t3
    jal kslot
    nop
    move $t3, $v0               /* 이후 배치 계산은 칸 번호로 */
    lw $ra, 0x90($sp)
    lw $a1, 0x94($sp)
    .word 0x7bb00000            /* lq s0 */
    .word 0x7bb10010
    .word 0x7bb20020
    .word 0x7bb30030
    .word 0x7bb40040
    .word 0x7bb50050
    .word 0x7bb60060
    .word 0x7bb70070
    .word 0x7bbe0080
    addiu $sp, $sp, 0xc0

    lui $t4, %hi(kdata)
    addiu $t4, $t4, %lo(kdata)
    lbu $v0, 0($t4)             /* 회전 카운터 */
    addiu $v0, $v0, 1
    sltiu $t1, $v0, 15
    bnez $t1, 1f
    nop
    move $v0, $zero
1:  sb $v0, 0($t4)
    addiu $v0, $v0, 0xf0        /* v0 = 슬롯 */

    lw $t1, 0x6ecc($a1)
    andi $t1, $t1, 2
    addiu $t5, $t4, 4           /* 작은 폰트 배치 */
    beqz $t1, 2f
    nop
    addiu $t5, $t4, 36          /* 큰 폰트 배치 */
2:  /* 배치: +0 cols, +4 gw, +8 ch, +12 x0, +16 y0, +20 1/W, +24 1/H, +28 행 표 주소 */
    lw $t1, 0($t5)
    divu $zero, $t3, $t1
    mflo $t6                    /* 행 */
    mfhi $t7                    /* 열 */
    lw $t1, 4($t5)              /* gw */
    multu $t7, $t1
    mflo $t7
    lw $t2, 12($t5)
    addu $t7, $t7, $t2          /* x */
    lw $t2, 8($t5)              /* ch */
    multu $t6, $t2
    mflo $t6
    lw $a2, 16($t5)
    addu $t6, $t6, $a2          /* y */

    sll $a2, $v0, 4
    addu $a2, $a2, $a1          /* UV 항목 = a2 + 0x6efc */
    lwc1 $f2, 20($t5)           /* 1/W */
    lwc1 $f3, 24($t5)           /* 1/H */
    mtc1 $t7, $f0
    cvt.s.w $f0, $f0
    mul.s $f0, $f0, $f2
    swc1 $f0, 0x6efc($a2)       /* u0 */
    addiu $a3, $t6, 1
    mtc1 $a3, $f0
    cvt.s.w $f0, $f0
    mul.s $f0, $f0, $f3
    swc1 $f0, 0x6f00($a2)       /* v0 */
    addu $a3, $t7, $t1
    mtc1 $a3, $f0
    cvt.s.w $f0, $f0
    mul.s $f0, $f0, $f2
    swc1 $f0, 0x6f04($a2)       /* u1 */
    addu $a3, $t6, $t2
    mtc1 $a3, $f0
    cvt.s.w $f0, $f0
    mul.s $f0, $f0, $f3
    swc1 $f0, 0x6f08($a2)       /* v1 */

    sll $a2, $v0, 2
    addu $a2, $a2, $a1
    sw $t1, 0x7ef4($a2)         /* 폭 */
    lui $a3, 1
    addu $a3, $a3, $a2
    sw $t1, -0x7d10($a3)        /* +0x82f0 */

    lw $a2, 28($t5)             /* 정적 행 표 */
    addiu $a3, $zero, 0x84
    multu $v0, $a3
    mflo $a3
    addu $a2, $a2, $a3
    sb $t1, 1($a2)
    jr $ra
    sb $zero, 3($a2)

single:
    addiu $t0, $t0, 1
    sw $t0, 0($a0)
    beqz $t8, 3f
    nop
    addiu $t1, $v1, -0x61
    sltiu $t1, $t1, 26
    bnez $t1, 4f
    addiu $t1, $v1, -0xe0
    sltiu $t1, $t1, 0x1d
    beqz $t1, 3f
    nop
4:  addiu $v1, $v1, -0x20
3:  beqz $v1, ret_ff
    addiu $t1, $zero, 0x20
    beq $v1, $t1, ret_ff
    addu $t1, $t9, $v1
    jr $ra
    lbu $v0, 0($t1)

ret_ff:
    jr $ra
    addiu $v0, $zero, 0xff

    .data
    .globl kdata
    .align 4
kdata:
    .word 0                     /* +0 회전 카운터 */
    .space 32                   /* +4 작은 폰트 배치 (빌드 시 채움) */
    .space 32                   /* +36 큰 폰트 배치 */
