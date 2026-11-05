; =====================================================================
; 04_buffer_overflow.asm
; Security Demonstration: Stack Canary & Boundary Protection.
; A buggy function allocates local buffer space and writes out of bounds,
; smashing the stack canary.
; The leave epilogue detects this and trips STACK_CANARY_CORRUPTED exception!
; =====================================================================

.text
.globl main

main:
    call vulnerable_function
    hlt                     ; Should never be reached if canary trips

vulnerable_function:
    enter 4                 ; Allocates 4 bytes of local buffer space below canary
    ; Stack layout:
    ;   [fp + 4] : Return Address
    ;   [fp + 0] : Old FP
    ;   [fp - 4] : Canary (0xDEADC0DE)
    ;   [fp - 8] : Local buffer [sp points here]

    ; Normal write to local buffer:
    mov r2, 1234
    st r2, 0[sp]            ; Safe write into local variable

    ; Out-of-bounds write attack: writes past local buffer into canary slot!
    mov r3, 0xBAD           ; Corrupted canary value
    st r3, 4[sp]            ; Overwrites [fp - 4] (the CANARY slot!)

    ; Attempt function return
    leave 4                 ; Checks canary -> Mismatch detected -> Triggers TRAP 6!
