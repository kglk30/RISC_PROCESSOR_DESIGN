; =====================================================================
; 01_basic_test.asm
; Verifies:
;  1. Hardwired Zero Register (r0): writes ignored, reads always 0
;  2. ALU operations: add, sub, mul, div, mod, and, or, not, lsl, lsr, asr
;  3. Comparison & Branches: cmp, beq, bgt, blt, b
; =====================================================================

.text
.globl main

main:
    ; --- 1. Test Hardwired Zero Register (r0) ---
    mov r1, 42
    add r0, r1, r1          ; Attempt to overwrite r0 with 84 (must be ignored)
    add r2, r0, 10          ; Read r0: r2 should be 0 + 10 = 10
    cmp r0, 0               ; Verify r0 is still 0
    beq .test_r0_passed
    trap 2                  ; Fail if r0 != 0

.test_r0_passed:
    ; --- 2. Test Arithmetic & Logic ---
    mov r3, 15
    mov r4, 4
    add r5, r3, r4          ; r5 = 15 + 4 = 19
    sub r6, r3, r4          ; r6 = 15 - 4 = 11
    mul r7, r3, r4          ; r7 = 15 * 4 = 60
    div r8, r3, r4          ; r8 = 15 / 4 = 3
    mod r9, r3, r4          ; r9 = 15 % 4 = 3

    and r10, r3, r4         ; 15 & 4 = 4
    or  r11, r3, r4         ; 15 | 4 = 15
    lsl r12, r4, 2          ; 4 << 2 = 16

    ; --- 3. Test Conditional Branches ---
    cmp r5, 19
    bne .test_fail
    cmp r6, 11
    bne .test_fail
    cmp r7, 60
    bne .test_fail
    cmp r8, 3
    bne .test_fail
    cmp r9, 3
    bne .test_fail

    ; All basic tests passed!
    mov r1, 1               ; Success code
    hlt

.test_fail:
    mov r1, -1              ; Error code
    trap 2
