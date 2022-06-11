#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>

int main(int argc, char **argv) {
	if (argc <= 1) {
		puts("That's not how you sudo!");
		return 1;
	}
	if (setresuid(0, 0, 0) != 0) {
		perror("setresuid");
		return 1;
	}
	if (setgid(0) != 0) {
		perror("setgid");
		return 1;
	}
	return execvp(argv[1], &argv[1]);
}
