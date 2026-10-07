// SPDX-License-Identifier: GPL-2.0-only OR MIT
/*
 * Apple SART device driver
 * Copyright (C) The Asahi Linux Contributors
 *
 * Apple SART is a simple address filter for some DMA transactions.
 * Regions of physical memory must be added to the SART's allow
 * list before any DMA can target these. Unlike a proper
 * IOMMU no remapping can be done and special support in the
 * consumer driver is required since not all DMA transactions of
 * a single device are subject to SART filtering.
 */

#include <linux/soc/apple/sart.h>
#include <linux/atomic.h>
#include <linux/bits.h>
#include <linux/bitfield.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/types.h>

#define APPLE_SART_MAX_ENTRIES 16

/* SARTv0 registers */
#define APPLE_SART0_CONFIG(idx)       (0x00 + 4 * (idx))
#define APPLE_SART0_CONFIG_FLAGS      GENMASK(28, 24)
#define APPLE_SART0_CONFIG_SIZE       GENMASK(18, 0)
#define APPLE_SART0_CONFIG_SIZE_SHIFT 12
#define APPLE_SART0_CONFIG_SIZE_MAX   GENMASK(18, 0)

#define APPLE_SART0_PADDR(idx)  (0x40 + 4 * (idx))
#define APPLE_SART0_PADDR_SHIFT 12

#define APPLE_SART0_FLAGS_ALLOW 0xf

/* SARTv2 registers */
#define APPLE_SART2_CONFIG(idx)	      (0x00 + 4 * (idx))
#define APPLE_SART2_CONFIG_FLAGS      GENMASK(31, 24)
#define APPLE_SART2_CONFIG_SIZE	      GENMASK(23, 0)
#define APPLE_SART2_CONFIG_SIZE_SHIFT 12
#define APPLE_SART2_CONFIG_SIZE_MAX   GENMASK(23, 0)

#define APPLE_SART2_PADDR(idx)	(0x40 + 4 * (idx))
#define APPLE_SART2_PADDR_SHIFT 12

#define APPLE_SART2_FLAGS_ALLOW 0xff

/* SARTv3 registers */
#define APPLE_SART3_CONFIG(idx) (0x00 + 4 * (idx))

#define APPLE_SART3_PADDR(idx)	(0x40 + 4 * (idx))
#define APPLE_SART3_PADDR_SHIFT 12

#define APPLE_SART3_SIZE(idx)  (0x80 + 4 * (idx))
#define APPLE_SART3_SIZE_SHIFT 12
#define APPLE_SART3_SIZE_MAX   GENMASK(29, 0)

#define APPLE_SART3_FLAGS_ALLOW 0xff

/* T8140 CoastGuard SART power-control protocol. */
#define APPLE_SART_POWER_ACTIVE          0
#define APPLE_SART_POWER_INACTIVE        1
#define APPLE_SART_POWER_DELAY_US        100
#define APPLE_SART_POWER_TIMEOUT_US      100000

struct apple_sart_ops {
	void (*get_entry)(struct apple_sart *sart, int index, u8 *flags,
			  phys_addr_t *paddr, size_t *size);
	void (*set_entry)(struct apple_sart *sart, int index, u8 flags,
			  phys_addr_t paddr_shifted, size_t size_shifted);
	/* This is probably a bitfield but the exact meaning of each bit is unknown. */
	unsigned int flags_allow;
	unsigned int size_shift;
	unsigned int paddr_shift;
	size_t size_max;
	bool power_managed;
};

struct apple_sart {
	struct device *dev;
	void __iomem *regs;
	void __iomem *power_reg;

	const struct apple_sart_ops *ops;
	struct mutex power_lock;
	unsigned int power_users;
	struct mutex entries_lock;
	bool entries_scanned;

	unsigned long protected_entries;
	unsigned long used_entries;
};

static void sart0_get_entry(struct apple_sart *sart, int index, u8 *flags,
	phys_addr_t *paddr, size_t *size)
{
	u32 cfg = readl(sart->regs + APPLE_SART0_CONFIG(index));
	phys_addr_t paddr_ = readl(sart->regs + APPLE_SART0_PADDR(index));
	size_t size_ = FIELD_GET(APPLE_SART0_CONFIG_SIZE, cfg);

	*flags = FIELD_GET(APPLE_SART0_CONFIG_FLAGS, cfg);
	*size = size_ << APPLE_SART0_CONFIG_SIZE_SHIFT;
	*paddr = paddr_ << APPLE_SART0_PADDR_SHIFT;
}

static void sart0_set_entry(struct apple_sart *sart, int index, u8 flags,
	phys_addr_t paddr_shifted, size_t size_shifted)
{
	u32 cfg;

	cfg = FIELD_PREP(APPLE_SART0_CONFIG_FLAGS, flags);
	cfg |= FIELD_PREP(APPLE_SART0_CONFIG_SIZE, size_shifted);

	writel(paddr_shifted, sart->regs + APPLE_SART0_PADDR(index));
	writel(cfg, sart->regs + APPLE_SART0_CONFIG(index));
}

static struct apple_sart_ops sart_ops_v0 = {
	.get_entry = sart0_get_entry,
	.set_entry = sart0_set_entry,
	.flags_allow = APPLE_SART0_FLAGS_ALLOW,
	.size_shift = APPLE_SART0_CONFIG_SIZE_SHIFT,
	.paddr_shift = APPLE_SART0_PADDR_SHIFT,
	.size_max = APPLE_SART0_CONFIG_SIZE_MAX,
};

static void sart2_get_entry(struct apple_sart *sart, int index, u8 *flags,
			    phys_addr_t *paddr, size_t *size)
{
	u32 cfg = readl(sart->regs + APPLE_SART2_CONFIG(index));
	phys_addr_t paddr_ = readl(sart->regs + APPLE_SART2_PADDR(index));
	size_t size_ = FIELD_GET(APPLE_SART2_CONFIG_SIZE, cfg);

	*flags = FIELD_GET(APPLE_SART2_CONFIG_FLAGS, cfg);
	*size = size_ << APPLE_SART2_CONFIG_SIZE_SHIFT;
	*paddr = paddr_ << APPLE_SART2_PADDR_SHIFT;
}

static void sart2_set_entry(struct apple_sart *sart, int index, u8 flags,
			    phys_addr_t paddr_shifted, size_t size_shifted)
{
	u32 cfg;

	cfg = FIELD_PREP(APPLE_SART2_CONFIG_FLAGS, flags);
	cfg |= FIELD_PREP(APPLE_SART2_CONFIG_SIZE, size_shifted);

	writel(paddr_shifted, sart->regs + APPLE_SART2_PADDR(index));
	writel(cfg, sart->regs + APPLE_SART2_CONFIG(index));
}

static struct apple_sart_ops sart_ops_v2 = {
	.get_entry = sart2_get_entry,
	.set_entry = sart2_set_entry,
	.flags_allow = APPLE_SART2_FLAGS_ALLOW,
	.size_shift = APPLE_SART2_CONFIG_SIZE_SHIFT,
	.paddr_shift = APPLE_SART2_PADDR_SHIFT,
	.size_max = APPLE_SART2_CONFIG_SIZE_MAX,
};

static void sart3_get_entry(struct apple_sart *sart, int index, u8 *flags,
			    phys_addr_t *paddr, size_t *size)
{
	phys_addr_t paddr_ = readl(sart->regs + APPLE_SART3_PADDR(index));
	size_t size_ = readl(sart->regs + APPLE_SART3_SIZE(index));

	*flags = readl(sart->regs + APPLE_SART3_CONFIG(index));
	*size = size_ << APPLE_SART3_SIZE_SHIFT;
	*paddr = paddr_ << APPLE_SART3_PADDR_SHIFT;
}

static void sart3_set_entry(struct apple_sart *sart, int index, u8 flags,
			    phys_addr_t paddr_shifted, size_t size_shifted)
{
	writel(paddr_shifted, sart->regs + APPLE_SART3_PADDR(index));
	writel(size_shifted, sart->regs + APPLE_SART3_SIZE(index));
	writel(flags, sart->regs + APPLE_SART3_CONFIG(index));
}

static struct apple_sart_ops sart_ops_v3 = {
	.get_entry = sart3_get_entry,
	.set_entry = sart3_set_entry,
	.flags_allow = APPLE_SART3_FLAGS_ALLOW,
	.size_shift = APPLE_SART3_SIZE_SHIFT,
	.paddr_shift = APPLE_SART3_PADDR_SHIFT,
	.size_max = APPLE_SART3_SIZE_MAX,
};

static struct apple_sart_ops sart_ops_v3_power_managed = {
	.get_entry = sart3_get_entry,
	.set_entry = sart3_set_entry,
	.flags_allow = APPLE_SART3_FLAGS_ALLOW,
	.size_shift = APPLE_SART3_SIZE_SHIFT,
	.paddr_shift = APPLE_SART3_PADDR_SHIFT,
	.size_max = APPLE_SART3_SIZE_MAX,
	.power_managed = true,
};

static u32 sart_set_power_state(struct apple_sart *sart, u32 state)
{
	writel(state, sart->power_reg);
	udelay(APPLE_SART_POWER_DELAY_US);

	return readl(sart->power_reg);
}

static int sart_power_get(struct apple_sart *sart)
{
	u32 state;
	int ret = 0;

	if (!sart->ops->power_managed)
		return 0;

	mutex_lock(&sart->power_lock);
	if (!sart->power_users) {
		ret = read_poll_timeout_atomic(sart_set_power_state, state,
					       state == APPLE_SART_POWER_ACTIVE,
					       0, APPLE_SART_POWER_TIMEOUT_US,
					       false, sart,
					       APPLE_SART_POWER_ACTIVE);
		if (ret)
			dev_err(sart->dev, "failed to activate SART: %#x\n",
				state);
	}
	if (!ret)
		sart->power_users++;
	mutex_unlock(&sart->power_lock);

	return ret;
}

static void sart_power_put(struct apple_sart *sart)
{
	u32 state;
	int ret;

	if (!sart->ops->power_managed)
		return;

	mutex_lock(&sart->power_lock);
	if (WARN_ON(!sart->power_users))
		goto out;

	if (--sart->power_users)
		goto out;

	ret = read_poll_timeout_atomic(sart_set_power_state, state,
				       state == APPLE_SART_POWER_INACTIVE,
				       0, APPLE_SART_POWER_TIMEOUT_US, false,
				       sart, APPLE_SART_POWER_INACTIVE);
	if (ret)
		dev_err(sart->dev, "failed to deactivate SART: %#x\n", state);

out:
	mutex_unlock(&sart->power_lock);
}

static void sart_scan_entries(struct apple_sart *sart)
{
	int i;

	mutex_lock(&sart->entries_lock);
	if (sart->entries_scanned)
		goto out;

	for (i = 0; i < APPLE_SART_MAX_ENTRIES; ++i) {
		u8 flags;
		size_t size;
		phys_addr_t paddr;

		sart->ops->get_entry(sart, i, &flags, &paddr, &size);

		if (!flags)
			continue;

		dev_dbg(sart->dev,
			"SART bootloader entry: index %02d; flags: 0x%02x; paddr: %pa; size: 0x%zx\n",
			i, flags, &paddr, size);
		set_bit(i, &sart->protected_entries);
	}
	sart->entries_scanned = true;
out:
	mutex_unlock(&sart->entries_lock);
}

static int apple_sart_probe(struct platform_device *pdev)
{
	struct resource *res;
	struct apple_sart *sart;
	struct device *dev = &pdev->dev;

	sart = devm_kzalloc(dev, sizeof(*sart), GFP_KERNEL);
	if (!sart)
		return -ENOMEM;

	sart->dev = dev;
	sart->ops = of_device_get_match_data(dev);
	mutex_init(&sart->power_lock);
	mutex_init(&sart->entries_lock);

	sart->regs = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(sart->regs))
		return PTR_ERR(sart->regs);

	if (sart->ops->power_managed) {
		res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "power");
		if (!res)
			return dev_err_probe(dev, -EINVAL,
					     "missing power register\n");

		/*
		 * CoastGuard's control register overlaps the ANS MMIO resource,
		 * so map the scalar subresource without claiming the whole range.
		 */
		sart->power_reg = devm_ioremap(dev, res->start,
					      resource_size(res));
		if (!sart->power_reg)
			return -ENOMEM;
	} else {
		sart_scan_entries(sart);
	}

	platform_set_drvdata(pdev, sart);
	return 0;
}

struct apple_sart *devm_apple_sart_get(struct device *dev)
{
	struct device_node *sart_node;
	struct platform_device *sart_pdev;
	struct apple_sart *sart;

	sart_node = of_parse_phandle(dev->of_node, "apple,sart", 0);
	if (!sart_node)
		return ERR_PTR(-ENODEV);

	sart_pdev = of_find_device_by_node(sart_node);
	of_node_put(sart_node);

	if (!sart_pdev)
		return ERR_PTR(-ENODEV);

	sart = dev_get_drvdata(&sart_pdev->dev);
	if (!sart) {
		put_device(&sart_pdev->dev);
		return ERR_PTR(-EPROBE_DEFER);
	}

	device_link_add(dev, &sart_pdev->dev,
			DL_FLAG_PM_RUNTIME | DL_FLAG_AUTOREMOVE_SUPPLIER);

	put_device(&sart_pdev->dev);

	return sart;
}
EXPORT_SYMBOL_GPL(devm_apple_sart_get);

static int sart_set_entry(struct apple_sart *sart, int index, u8 flags,
			  phys_addr_t paddr, size_t size)
{
	if (size & ((1 << sart->ops->size_shift) - 1))
		return -EINVAL;
	if (paddr & ((1 << sart->ops->paddr_shift) - 1))
		return -EINVAL;

	paddr >>= sart->ops->size_shift;
	size >>= sart->ops->paddr_shift;

	if (size > sart->ops->size_max)
		return -EINVAL;

	sart->ops->set_entry(sart, index, flags, paddr, size);
	return 0;
}

int apple_sart_add_allowed_region(struct apple_sart *sart, phys_addr_t paddr,
				  size_t size)
{
	int i, ret;

	ret = sart_power_get(sart);
	if (ret)
		return ret;
	sart_scan_entries(sart);

	for (i = 0; i < APPLE_SART_MAX_ENTRIES; ++i) {
		if (test_bit(i, &sart->protected_entries))
			continue;
		if (test_and_set_bit(i, &sart->used_entries))
			continue;

		ret = sart_set_entry(sart, i, sart->ops->flags_allow, paddr,
				     size);
		if (ret) {
			dev_dbg(sart->dev,
				"unable to set entry %d to [%pa, 0x%zx]\n",
				i, &paddr, size);
			clear_bit(i, &sart->used_entries);
			sart_power_put(sart);
			return ret;
		}

		dev_dbg(sart->dev, "wrote [%pa, 0x%zx] to %d\n", &paddr, size,
			i);
		return 0;
	}

	dev_warn(sart->dev,
		 "no free entries left to add [paddr: 0x%pa, size: 0x%zx]\n",
		 &paddr, size);
	sart_power_put(sart);

	return -EBUSY;
}
EXPORT_SYMBOL_GPL(apple_sart_add_allowed_region);

int apple_sart_remove_allowed_region(struct apple_sart *sart, phys_addr_t paddr,
				     size_t size)
{
	int i, ret;

	dev_dbg(sart->dev,
		"will remove [paddr: %pa, size: 0x%zx] from allowed regions\n",
		&paddr, size);

	ret = sart_power_get(sart);
	if (ret)
		return ret;
	sart_scan_entries(sart);

	for (i = 0; i < APPLE_SART_MAX_ENTRIES; ++i) {
		u8 eflags;
		size_t esize;
		phys_addr_t epaddr;

		if (test_bit(i, &sart->protected_entries))
			continue;

		sart->ops->get_entry(sart, i, &eflags, &epaddr, &esize);

		if (epaddr != paddr || esize != size)
			continue;

		sart->ops->set_entry(sart, i, 0, 0, 0);

		clear_bit(i, &sart->used_entries);
		dev_dbg(sart->dev, "cleared entry %d\n", i);
		/* Drop the region's persistent reference and this lookup's. */
		sart_power_put(sart);
		sart_power_put(sart);
		return 0;
	}

	dev_warn(sart->dev, "entry [paddr: 0x%pa, size: 0x%zx] not found\n",
		 &paddr, size);
	sart_power_put(sart);

	return -EINVAL;
}
EXPORT_SYMBOL_GPL(apple_sart_remove_allowed_region);

static void apple_sart_shutdown(struct platform_device *pdev)
{
	struct apple_sart *sart = dev_get_drvdata(&pdev->dev);
	int i;

	/* An unused power-managed SART is already quiescent. */
	if (sart->ops->power_managed && !READ_ONCE(sart->used_entries))
		return;

	if (sart_power_get(sart))
		return;

	for (i = 0; i < APPLE_SART_MAX_ENTRIES; ++i) {
		if (test_bit(i, &sart->protected_entries))
			continue;

		sart->ops->set_entry(sart, i, 0, 0, 0);
	}

	for (i = 0; i < APPLE_SART_MAX_ENTRIES; ++i) {
		if (test_and_clear_bit(i, &sart->used_entries))
			sart_power_put(sart);
	}
	sart_power_put(sart);
}

static const struct of_device_id apple_sart_of_match[] = {
	{
		.compatible = "apple,t8140-sart",
		.data = &sart_ops_v3_power_managed,
	},
	{
		.compatible = "apple,t6000-sart",
		.data = &sart_ops_v3,
	},
	{
		.compatible = "apple,t8103-sart",
		.data = &sart_ops_v2,
	},
	{
		.compatible = "apple,t8015-sart",
		.data = &sart_ops_v0,
	},
	{}
};
MODULE_DEVICE_TABLE(of, apple_sart_of_match);

static struct platform_driver apple_sart_driver = {
	.driver = {
		.name = "apple-sart",
		.of_match_table = apple_sart_of_match,
	},
	.probe = apple_sart_probe,
	.shutdown = apple_sart_shutdown,
};
module_platform_driver(apple_sart_driver);

MODULE_LICENSE("Dual MIT/GPL");
MODULE_AUTHOR("Sven Peter <sven@svenpeter.dev>");
MODULE_DESCRIPTION("Apple SART driver");
