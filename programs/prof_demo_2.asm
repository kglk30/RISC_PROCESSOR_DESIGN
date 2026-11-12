.text
main:
    mov r1, 42
    call corrupt_frame
    hlt

corrupt_frame:
    enter 0
    mov r2, 0
    st r2, 0[sp]
    leave 0
