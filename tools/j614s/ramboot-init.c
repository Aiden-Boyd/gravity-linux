// SPDX-License-Identifier: MIT
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <unistd.h>

static void dump_file(const char *path)
{
	char buf[4096];
	int fd = open(path, O_RDONLY);
	ssize_t n;

	if (fd < 0) {
		dprintf(STDOUT_FILENO, "%s: open failed: %s\n", path, strerror(errno));
		return;
	}

	while ((n = read(fd, buf, sizeof(buf))) > 0)
		write(STDOUT_FILENO, buf, n);

	close(fd);
}

int main(void)
{
	struct utsname u;

	mkdir("/proc", 0755);
	mkdir("/sys", 0755);
	mkdir("/dev", 0755);

	mount("proc", "/proc", "proc", 0, NULL);
	mount("sysfs", "/sys", "sysfs", 0, NULL);
	mount("devtmpfs", "/dev", "devtmpfs", 0, NULL);

	printf("\n=== J614S_RAMBOOT_OK ===\n");
	if (!uname(&u))
		printf("kernel: %s %s %s\n", u.sysname, u.release, u.machine);

	printf("model: ");
	fflush(stdout);
	dump_file("/proc/device-tree/model");
	printf("\n\n/proc/cpuinfo:\n");
	dump_file("/proc/cpuinfo");

	printf("\n=== RAM-only diagnostic reached userspace ===\n");
	printf("No root filesystem is mounted. Leave power connected; power-cycle to exit.\n");
	fflush(stdout);

	for (;;)
		sleep(3600);
}
