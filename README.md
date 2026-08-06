# builda-bytecodevm
Git repo for transpiling C code into Bytecode for a VM made in Builda.

## How to compile
Simply run the transpile script with your .c or .s file to get a string you can paste into the VM
`python3 transpile.py code.s -o instructions.txt`
or you can directly copy it to your clipboard if your using Termux (Android)
```bash
pkg install termux-api
python3 transpile.py assembly.s | termux-clipboard-set
```
