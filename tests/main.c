#include <stdio.h>

/* Compilation:
zig cc -target x86_64-linux-musl -static main.c -o main-static
zig cc -target x86_64-linux-gnu main.c -o main-dynamic
*/

int main()
{
    puts("Hello from Rosetta!");
}
