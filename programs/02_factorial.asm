; =====================================================================
; 02_factorial.asm
; Recursive Factorial: computes fact(5) = 120.
; Stresses full-descending stack, enter/leave macros, and stack canaries.
; =====================================================================

.text
.globl main

main:
    mov r1, 5               ; Argument n = 5
    push r1                 ; Push argument to stack
    call fact
    pop r2                  ; Pop argument
    ; Result is in r1 (expected: 120)
    mov r3, 120
    cmp r1, r3
    beq .success
    trap 2                  ; Failure trap

.success:
    hlt

; ---------------------------------------------------------------------
; fact(n) -> returns result in r1
; Stack layout:
;   [fp + 8] : Argument n
;   [fp + 4] : Saved return address (RA)
;   [fp + 0] : Saved frame pointer (FP)
;   [fp - 4] : Stack Canary (0xDEADC0DE)
; ---------------------------------------------------------------------
fact:
    enter 0                 ; Prologue: saves RA, FP, and inserts Canary

    ld r2, 8[fp]            ; Load argument n

    ; Base condition: if n <= 1 return 1
    cmp r2, 1
    bgt .recurse
    mov r1, 1               ; Base case: return 1
    b .fact_exit

.recurse:
    sub r3, r2, 1           ; n - 1
    push r2                 ; Save current n
    push r3                 ; Push (n - 1) as argument
    call fact
    pop r3                  ; Pop argument
    pop r2                  ; Restore current n

    mul r1, r1, r2          ; r1 = fact(n - 1) * n

.fact_exit:
    leave 0                 ; Epilogue: checks canary, restores FP and RA, returns
