SECTIONS {
  . = 0xa0000;
  .k : { *(.text*) *(.data*) *(.rodata*) *(.sdata*) *(.sbss*) *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.comment) *(.pdr) *(.gnu.attributes) *(.eh_frame*) *(.MIPS.options) }
}
