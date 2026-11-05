; =====================================================================
; 03_fibonacci.asm
; Recursive Fibonacci: computes fib(6) = 8.
; Deep stack recursion, verifying activation records and canaries.
; =====================================================================

.text
.globl main

main:
    mov r1, 6               ; n = 6
    push r1
    call fib
    pop r2
    ; Result in r1 (expected: 8)
    cmp r1, 8
    beq .fib_ok
    trap 2

.fib_ok:
    hlt

; ---------------------------------------------------------------------
; fib(n):
; if n == 0 return 0
; if n == 1 return 1
; return fib(n-1) + fib(n-2)
; ---------------------------------------------------------------------
fib:
    enter 0
    ld r2, 8[fp]            ; Read n

    cmp r2, 0
    beq .ret_zero
    cmp r2, 1
    beq .ret_one

    ; Calculate fib(n-1)
    sub r3, r2, 1
    push r2                 ; Save n
    push r3
    call fib
    pop r3
    pop r2

    push r1                 ; Save fib(n-1) result

    ; Calculate fib(n-2)
    sub r3, r2, 2
    push r2                 ; Save n
    push r3
    call fib
    pop r3
    pop r2

    pop r4                  ; Restore fib(n-1) result
    add r1, r1, r4          ; r1 = fib(n-1) + fib(n-2)
    b .fib_exit

.ret_zero:
    mov r1, 0
    b .fib_exit

.ret_one:
    mov r1, 1

.fib_exit:
    leave 0
