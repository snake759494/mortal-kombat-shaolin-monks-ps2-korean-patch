/* 한글 글리프 동적 캐시
 *
 * 폰트 텍스처 아래쪽(y0 이후)을 gw x ch 캐시 칸으로 나눠, 그려야 할 한글 음절을 LRU 로 칸에 넣는다.
 * 칸이 바뀌면 RAM 의 캐시 영상(4bpp, 텍스처 폭 그대로)에 글리프를 복사하고, 그 칸의 행 띠(W x ch)를
 * GIF DMA(채널 2, 체인)로 텍스처 VRAM 에 직접 올린 뒤 TEXFLUSH 한다.
 * kdec.S 가 sq 로 s 레지스터를 보존한 뒤 kslot() 을 부른다.
 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define NK 2400
#define CAP 168
#define UNC(p) ((volatile u32 *)(0x20000000u | (u32)(p)))
#define PHYS(p) ((u32)(p) & 0x0fffffffu)
#define D2_CHCR (*(volatile u32 *)0x1000a000)
#define D2_QWC (*(volatile u32 *)0x1000a020)
#define D2_TADR (*(volatile u32 *)0x1000a030)

struct kf {
    u32 kcols, gw, ch, y0, W, cap, bpp;   /* 빌드 시 채움 */
    u8 *glyph;                            /* 글리프 저장소 */
    u8 *cache;                            /* 캐시 영상(행 y0 부터) */
    u32 clock;
    u16 slot_of_k[NK];                    /* 칸+1, 0 = 없음 */
    u16 k_of_slot[CAP];                   /* k+1 */
    u32 stamp[CAP];
};

struct kf kf_small = {1}, kf_big = {1};
static u32 pk[44] __attribute__((aligned(16)));

void *memset(void *d, int c, u32 n) { u8 *p = d; while (n--) *p++ = (u8)c; return d; }
void *memcpy(void *d, const void *s, u32 n) { u8 *p = d; const u8 *q = s; while (n--) *p++ = *q++; return d; }

static u32 di(void)
{
    u32 st;
    __asm__ volatile("mfc0 %0, $12" : "=r"(st));
    for (;;) {
        u32 s2;
        __asm__ volatile(".word 0x42000039\n\t.word 0x0000040f\n\tmfc0 %0, $12" : "=r"(s2) :: "memory"); /* di; sync.p */
        if (!(s2 & 0x10000)) break;
    }
    return st & 0x10000;
}

static void ei(u32 was)
{
    if (was) __asm__ volatile(".word 0x42000038" ::: "memory");
}

static void upload(struct kf *f, u32 fontobj, u32 row)
{
    u32 mgr = *(u32 *)0x4efe94;
    u32 tex = *(u32 *)(mgr + 0x20) + *(u32 *)(fontobj + 0x6ef8) * 0x430;
    u32 dbp = *(u32 *)(tex + 0x20);
    u32 W = f->W, h = f->ch, y = f->y0 + row * h;
    u32 qwc = W * h / 32;
    volatile u32 *p = UNC(pk);
    u32 was;

    p[0] = 6 | (1u << 28); p[1] = 0; p[2] = 0; p[3] = 0;                      /* DMA cnt 6qw */
    p[4] = 4; p[5] = 1u << 28; p[6] = 0xe; p[7] = 0;                          /* GIFtag A+D x4 */
    p[8] = 0; p[9] = dbp | ((W / 64) << 16) | (0x14u << 24); p[10] = 0x50; p[11] = 0;   /* BITBLTBUF PSMT4 */
    p[12] = 0; p[13] = y << 16; p[14] = 0x51; p[15] = 0;                     /* TRXPOS */
    p[16] = W; p[17] = h; p[18] = 0x52; p[19] = 0;                           /* TRXREG */
    p[20] = 0; p[21] = 0; p[22] = 0x53; p[23] = 0;                           /* TRXDIR 호스트→로컬 */
    p[24] = qwc; p[25] = 2u << 26; p[26] = 0; p[27] = 0;                     /* GIFtag IMAGE */
    p[28] = qwc | (3u << 28); p[29] = PHYS(f->cache + row * h * W / 2); p[30] = 0; p[31] = 0;  /* DMA ref */
    p[32] = 2 | (7u << 28); p[33] = 0; p[34] = 0; p[35] = 0;                 /* DMA end 2qw */
    p[36] = 1 | (1u << 15); p[37] = 1u << 28; p[38] = 0xe; p[39] = 0;        /* GIFtag EOP A+D */
    p[40] = 0; p[41] = 0; p[42] = 0x3f; p[43] = 0;                           /* TEXFLUSH */
    for (;;) {
        while (D2_CHCR & 0x100) ;
        was = di();
        if (!(D2_CHCR & 0x100)) break;
        ei(was);
    }
    __asm__ volatile(".word 0x0000000f" ::: "memory");                     /* sync.l */
    D2_QWC = 0;
    D2_TADR = PHYS(pk);
    D2_CHCR = 0x105;
    while (D2_CHCR & 0x100) ;
    ei(was);
}

int kslot(u32 k, u32 fontobj)
{
    struct kf *f = (*(u32 *)(fontobj + 0x6ecc) & 2) ? &kf_big : &kf_small;
    u32 s, i, best, r, x;
    f->clock++;
    if (k >= NK) k = 0;
    s = f->slot_of_k[k];
    if (s) {
        f->stamp[s - 1] = f->clock;
        return s - 1;
    }
    best = 0;
    for (i = 1; i < f->cap; i++)
        if (f->stamp[i] < f->stamp[best]) best = i;
    if (f->k_of_slot[best]) f->slot_of_k[f->k_of_slot[best] - 1] = 0;
    f->k_of_slot[best] = k + 1;
    f->slot_of_k[k] = best + 1;
    f->stamp[best] = f->clock;

    {
        u32 col = best % f->kcols, row = best / f->kcols;
        u32 stride = f->W / 2, gb = f->gw / 2;
        volatile u8 *d = (volatile u8 *)(0x20000000u | (u32)(f->cache + row * f->ch * stride + col * gb));
        if (f->bpp == 4) {
            const u8 *g = f->glyph + k * gb * f->ch;
            for (r = 0; r < f->ch; r++, d += stride)
                for (x = 0; x < gb; x++) d[x] = *g++;
        } else {
            const u8 *g = f->glyph + k * 2 * f->ch;
            for (r = 0; r < f->ch; r++, d += stride, g += 2) {
                u32 bits = g[0] | (g[1] << 8);
                for (x = 0; x < gb; x++)
                    d[x] = ((bits >> (2 * x)) & 1 ? 0x08 : 0) | ((bits >> (2 * x + 1)) & 1 ? 0x80 : 0);
            }
        }
        upload(f, fontobj, row);
    }
    return best;
}
