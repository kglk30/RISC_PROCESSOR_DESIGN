; =====================================================================
; 07_vector_dot.asm
; Vector Dot Product Benchmark
; Computes dot product of two 5-element vectors:
;   A = [1, 2, 3, 4, 5]
;   B = [10, 20, 30, 40, 50]
;   Expected result: 1*10 + 2*20 + 3*30 + 4*40 + 5*50 = 550
; Demonstrates data memory access, looping, and multiply-accumulate (MAC).
; =====================================================================

.data
vec_a:
    .word 1, 2, 3, 4, 5
vec_b:
    .word 10, 20, 30, 40, 50

.text
.globl main

main:
    mov r1, vec_a           ; Base address of vector A
    mov r2, vec_b           ; Base address of vector B
    mov r3, 5               ; Loop counter = 5
    mov r4, 0               ; Accumulator (sum = 0)

.dot_loop:
    cmp r3, 0
    beq .dot_done

    ld r5, 0[r1]            ; Load A[i]
    ld r6, 0[r2]            ; Load B[i]
    mul r7, r5, r6          ; A[i] * B[i]
    add r4, r4, r7          ; sum += A[i] * B[i]

    add r1, r1, 4           ; Advance pointer A
    add r2, r2, 4           ; Advance pointer B
    sub r3, r3, 1           ; Decrement counter
    b .dot_loop

.dot_done:
    ; Verify result is 550
    mov r8, 550
    cmp r4, r8
    beq .success
    trap 2                  ; Fail

.success:
    mov r1, r4              ; Return dot product in r1
    hlt
