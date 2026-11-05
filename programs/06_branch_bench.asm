; =====================================================================
; 06_branch_bench.asm
; Branch Predictor Benchmark
; Nested loops that evaluate branch prediction accuracy and CPI penalties.
; =====================================================================

.text
.globl main

main:
    mov r1, 0               ; Total accumulator
    mov r2, 20              ; Outer loop counter = 20

.outer_loop:
    mov r3, 10              ; Inner loop counter = 10

.inner_loop:
    add r1, r1, 1           ; Accumulate
    sub r3, r3, 1           ; Decrement inner counter
    cmp r3, 0
    bgt .inner_loop         ; Inner loop branch (taken 9 times, not taken 1 time)

    sub r2, r2, 1           ; Decrement outer counter
    cmp r2, 0
    bgt .outer_loop         ; Outer loop branch

    hlt
