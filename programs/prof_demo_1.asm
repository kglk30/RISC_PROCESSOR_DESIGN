.text
main:
    mov r1, 7
    push r1
    mov r1, 0
    pop r1
    mov r10, r1
    call square
    call add_three
    hlt

square:
    enter_leaf 0
    mul r4, r10, r10
    leave_leaf 0

add_three:
    enter 0
    add r1, r4, 3
    leave 0
