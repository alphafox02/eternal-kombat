"""Run EC's own unpacker (SUB.BIN $11784) on a .PL resource, whole frame at once (d6 bit 6 = no yield)."""
import unicorn as U, unicorn.m68k_const as M
SUB_BASE, UNPACK = 0x6000, 0x11784
PL_AT, OUT_AT, OBJ_AT, STOP = 0x40000, 0x70000, 0x7C000, 0x7FF00
class Unpacker:
    def __init__(self, sub):
        self.mu = mu = U.Uc(U.UC_ARCH_M68K, U.UC_MODE_BIG_ENDIAN)
        try: mu.ctl_set_cpu_model(M.UC_CPU_M68K_M68000)
        except Exception: pass
        mu.mem_map(0, 0x80000)
        mu.mem_write(SUB_BASE, sub)
        mu.mem_write(STOP, b'\x4e\x71' * 4)
        self.pl = None
    def load(self, pl):
        assert len(pl) <= OUT_AT - PL_AT
        self.mu.mem_write(PL_AT, pl); self.pl = pl
    def frame(self, res, n, trace=False):
        mu = self.mu
        mu.mem_write(OBJ_AT, bytes(0x200))
        mu.mem_write(OBJ_AT + 0x19E, b'\xff\xff')
        mu.mem_write(OBJ_AT + 0x1A, n.to_bytes(2, 'big'))
        sp = 0x7FE00
        mu.mem_write(sp, STOP.to_bytes(4, 'big'))
        for r, v in ((M.UC_M68K_REG_A7, sp), (M.UC_M68K_REG_A0, PL_AT + res), (M.UC_M68K_REG_A1, OUT_AT),
                     (M.UC_M68K_REG_A5, OBJ_AT), (M.UC_M68K_REG_A6, 0x30000), (M.UC_M68K_REG_D0, n & 0xFF),
                     (M.UC_M68K_REG_D6, 0x40)):
            mu.reg_write(r, v)
        mu.emu_start(UNPACK, STOP, timeout=5_000_000, count=5_000_000)
        end = mu.reg_read(M.UC_M68K_REG_A1)
        size = end - OUT_AT
        if not 0 <= size <= 0x4000: raise ValueError(f'bad size {size}')
        return bytes(mu.mem_read(OUT_AT, size))
