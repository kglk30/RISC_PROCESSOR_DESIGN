; =====================================================================
; 08_leaf_bench.asm
; Leaf Function Optimization Benchmark
; Demonstrates and verifies leaf function calls with enter_leaf / leave_leaf,
; avoiding saving the return address and frame pointer when safe.
; =====================================================================

.text
.globl main

main:
    mov r1, 10              ; Iteration limit = 10
    mov r2, 0               ; Accumulator = 0
    mov r3, 1               ; Loop counter i = 1

.loop:
    cmp r3, r1
    bgt .done

    ; Pass argument i in r10, call optimized leaf function
    mov r10, r3
    call leaf_square        ; Call leaf function (no nested calls inside)
    add r2, r2, r4          ; Accumulate square result from r4

    add r3, r3, 1           ; i++
    b .loop

.done:
    ; Expected sum of squares for 1..10 = 1+4+9+16+25+36+49+64+81+100 = 385
    mov r5, 385
    cmp r2, r5
    beq .ok
    trap 2                  ; Verification failure trap

.ok:
    mov r1, r2              ; r1 = 385
    hlt

; ---------------------------------------------------------------------
; leaf_square(x in r10) -> returns x^2 in r4
; Leaf subroutine: does not call any other functions.
; Avoids saving the return address (ra) and frame pointer (fp) to stack.
; ---------------------------------------------------------------------
leaf_square:
    enter_leaf 0            ; Leaf prologue: avoids saving RA & FP
    mul r4, r10, r10        ; r4 = x * x
    leave_leaf 0            ; Leaf epilogue: avoids restoring FP & RA, returns via ra
