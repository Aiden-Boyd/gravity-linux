# J614s power-thin bring-up

Purpose: test battery/power telemetry, sensors, lid/power-key input, RTC and
cluster cpufreq on top of SMC-thin without exercising endpoint power GPIOs.

The SMC core stays built in, while each consumer remains a module so it can be
loaded and inspected independently. SMC GPIO and reboot control stay disabled.

The DT reuses the reviewed J614s cluster DVFS description from the full
diagnostic tree, including the measured 4E + 5P + 5P OPP tables. No PCIe
endpoint is powered.

A pass admits each consumer separately; one failing module does not imply that
the other SMC consumers are rejected.
