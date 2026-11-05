; =====================================================================
; 05_hazard_bench.asm
; Data Hazard Benchmark
; Heavy RAW (Read-After-Write) dependencies and Load-Use delays.
; Evaluates efficiency of Full-Matrix Multiplexer Forwarding Network.
; =====================================================================

.data
buffer:
    .word 10, 20, 30, 40

.text
.globl main

main:
    mov r1, 10
    mov r2, 20

    ; --- Test 1: Immediate Back-to-Back RAW Dependencies ---
    ; Forwarding network routes EX-to-EX: 0 stalls with forwarding!
    ; Without forwarding: stalls 2-3 cycles per instruction!
    add r3, r1, r2          ; r3 = 10 + 20 = 30
    add r4, r3, r1          ; RAW on r3: r4 = 30 + 10 = 40
    sub r5, r4, r2          ; RAW on r4: r5 = 40 - 20 = 20
    mul r6, r5, r3          ; RAW on r5 and r3: r6 = 20 * 30 = 600

    ; --- Test 2: Chained Dependencies ---
    add r7, r6, 1
    add r8, r7, 2
    add r9, r8, 3
    add r10, r9, 4

    ; --- Test 3: Load-Use Hazard ---
    ; ld requires 1 cycle stall even with forwarding, but 2-3 stalls without
    mov r11, buffer
    ld r12, 0[r11]          ; Load buffer[0]
    add r1, r12, 5          ; Immediate use of loaded value!
    ld r2, 4[r11]           ; Load buffer[1]
    add r3, r2, r1          ; Immediate use

    hlt
