.text
main:
    mov r1, 5
    call factorial
    mov r1, r2
    hlt

factorial:
    enter 4
    st r1, 0[sp]
    cmp r1, 1
    bgt recurse
    mov r2, 1
    leave 4

recurse:
    sub r1, r1, 1
    call factorial
    ld r3, 0[sp]
    mul r2, r2, r3
    leave 4
