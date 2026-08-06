#!/usr/bin/env python3
# Thanks Gemini for helping me with some parts of the transpiler. Don't worry though, I coded the VM without AI!
import sys
import re
import struct
import argparse
import subprocess
import shutil
import tempfile
import os

# Opcodes
OP_PUSH    = 1
OP_POP     = 2
OP_LOAD32  = 3
OP_STORE32 = 4
OP_LOAD8   = 5
OP_STORE8  = 6
OP_ADD     = 16
OP_SUB     = 17
OP_MUL     = 18
OP_DIV     = 19
OP_AND     = 20
OP_OR      = 21
OP_SHL     = 23
OP_SHR     = 24
OP_JMP     = 32
OP_JZ      = 33
OP_CALL    = 34
OP_RET     = 35
OP_DRAW    = 48
OP_HALT    = 255

# Reserve RAM 1000+ for x86 CPU Registers
REG_MAP = {
    "%eax": 1000,
    "%ebx": 1004,
    "%ecx": 1008,
    "%edx": 1012,
    "%esi": 1016,
    "%edi": 1020,
    "%esp": 1024,
    "%ebp": 1028
}

class GCCAssemblyToVM:
    def __init__(self):
        self.bytes = []
        self.labels = {}
        self.fixups = []  # (byte_offset, label_name)

    def emit_byte(self, b):
        self.bytes.append(b)

    def emit_u32(self, val):
        packed = struct.pack("<I", val & 0xFFFFFFFF)
        for b in packed:
            self.bytes.append(b)

    def parse_operand(self, op_str):
        op_str = op_str.strip()
        if op_str in REG_MAP:
            return ('REG', REG_MAP[op_str])
        elif op_str.startswith('$'):
            val = int(op_str[1:])
            return ('IMM', val)
        elif '(' in op_str and ')' in op_str:
            # Memory dereference like -4(%ebp)
            match = re.match(r'(-?\d+)?\((%e\w+)\)', op_str)
            if match:
                offset = int(match.group(1)) if match.group(1) else 0
                base_reg = REG_MAP[match.group(2)]
                return ('MEM_OFF', base_reg, offset)
        return ('UNKNOWN', op_str)

    def load_operand_to_stack(self, parsed_op):
        kind = parsed_op[0]
        if kind == 'IMM':
            self.emit_byte(OP_PUSH)
            self.emit_u32(parsed_op[1])
        elif kind == 'REG':
            self.emit_byte(OP_PUSH)
            self.emit_u32(parsed_op[1])
            self.emit_byte(OP_LOAD32)
        elif kind == 'MEM_OFF':
            # Compute base_reg + offset
            base_reg_addr, offset = parsed_op[1], parsed_op[2]
            self.emit_byte(OP_PUSH)
            self.emit_u32(base_reg_addr)
            self.emit_byte(OP_LOAD32)
            if offset != 0:
                self.emit_byte(OP_PUSH)
                self.emit_u32(abs(offset))
                self.emit_byte(OP_SUB if offset < 0 else OP_ADD)
            self.emit_byte(OP_LOAD32)

    def transpile(self, asm_content):
        lines = asm_content.splitlines()

        for line in lines:
            line = line.strip()
            if not line or line.startswith('.') or line.startswith('#'):
                if line.endswith(':') and not line.startswith('.LFB'):
                    lbl = line[:-1].strip()
                    self.labels[lbl] = len(self.bytes) + 1
                continue

            line = line.split('#')[0].strip()
            if not line:
                continue

            parts = line.split(maxsplit=1)
            mnemonic = parts[0]
            args = [a.strip() for a in parts[1].split(',')] if len(parts) > 1 else []

            # --- TRANSLATE INSTRUCTIONS ---
            if mnemonic in ('movl', 'mov'):
                src, dst = self.parse_operand(args[0]), self.parse_operand(args[1])
                self.load_operand_to_stack(src)
                if dst[0] == 'REG':
                    self.emit_byte(OP_PUSH)
                    self.emit_u32(dst[1])
                    self.emit_byte(OP_STORE32)

            elif mnemonic in ('addl', 'add'):
                src, dst = self.parse_operand(args[0]), self.parse_operand(args[1])
                self.load_operand_to_stack(dst)
                self.load_operand_to_stack(src)
                self.emit_byte(OP_ADD)
                if dst[0] == 'REG':
                    self.emit_byte(OP_PUSH)
                    self.emit_u32(dst[1])
                    self.emit_byte(OP_STORE32)

            elif mnemonic in ('subl', 'sub'):
                src, dst = self.parse_operand(args[0]), self.parse_operand(args[1])
                self.load_operand_to_stack(dst)
                self.load_operand_to_stack(src)
                self.emit_byte(OP_SUB)
                if dst[0] == 'REG':
                    self.emit_byte(OP_PUSH)
                    self.emit_u32(dst[1])
                    self.emit_byte(OP_STORE32)

            elif mnemonic in ('imull', 'imul'):
                src, dst = self.parse_operand(args[0]), self.parse_operand(args[1])
                self.load_operand_to_stack(dst)
                self.load_operand_to_stack(src)
                self.emit_byte(OP_MUL)
                if dst[0] == 'REG':
                    self.emit_byte(OP_PUSH)
                    self.emit_u32(dst[1])
                    self.emit_byte(OP_STORE32)

            elif mnemonic == 'jmp':
                self.emit_byte(OP_JMP)
                self.fixups.append((len(self.bytes), args[0]))
                self.emit_u32(0)

            elif mnemonic in ('je', 'jz'):
                self.emit_byte(OP_JZ)
                self.fixups.append((len(self.bytes), args[0]))
                self.emit_u32(0)

            elif mnemonic == 'call':
                self.emit_byte(OP_CALL)
                self.fixups.append((len(self.bytes), args[0]))
                self.emit_u32(0)

            elif mnemonic == 'ret':
                self.emit_byte(OP_RET)

        self.emit_byte(OP_HALT)

        # --- RESOLVE LABEL ADDRESSES ---
        for offset, lbl in self.fixups:
            if lbl in self.labels:
                target_addr = self.labels[lbl]
                packed = struct.pack("<I", target_addr)
                for i, b in enumerate(packed):
                    self.bytes[offset + i] = b

        return ",".join(str(b) for b in self.bytes)


def compile_c_to_asm(c_path, opt_level):
    if not shutil.which("gcc"):
        sys.stderr.write("Error: 'gcc' compiler not found in PATH.\n")
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".s", delete=False) as tmp_asm:
        tmp_asm_path = tmp_asm.name

    cmd = [
        "gcc",
        f"-O{opt_level}",
        "-S",
        "-m32",
        "-fno-asynchronous-unwind-tables",
        c_path,
        "-o",
        tmp_asm_path,
    ]

    try:
        subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)
        with open(tmp_asm_path, "r") as f:
            asm_content = f.read()
        return asm_content
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"GCC Compilation Error:\n{e.stderr}\n")
        sys.exit(1)
    finally:
        if os.path.exists(tmp_asm_path):
            os.remove(tmp_asm_path)


def main():
    parser = argparse.ArgumentParser(
        description="Transpile C or x86 assembly (.s) to Builda VM bytecode (CSV payload)."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input file (.c, .s, or '-' for stdin). Defaults to stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output destination file. Prints to stdout if omitted.",
    )
    parser.add_argument(
        "-O",
        "--optimize",
        type=int,
        choices=[0, 1, 2, 3],
        default=1,
        help="GCC optimization level (0-3). Only used when input is a .c file. Default is 1.",
    )

    args = parser.parse_args()
  
    if args.input == "-":
        asm_content = sys.stdin.read()
    elif args.input.endswith(".c"):
        asm_content = compile_c_to_asm(args.input, args.optimize)
    else:
        try:
            with open(args.input, "r") as f:
                asm_content = f.read()
        except FileNotFoundError:
            sys.stderr.write(f"Error: File '{args.input}' not found.\n")
            sys.exit(1)

    transpiler = GCCAssemblyToVM()
    payload = transpiler.transpile(asm_content)
  
    if args.output:
        with open(args.output, "w") as f:
            f.write(payload + "\n")
    else:
        print(payload)


if __name__ == "__main__":
    main()
