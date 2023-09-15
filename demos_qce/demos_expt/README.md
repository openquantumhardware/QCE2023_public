This folder's demos use a loopback configuration of DAC 230_2 and ADC 226_2.

For Mixer-free readout the loopback should be moved to the 5-6 GHz baluns for best perfomance.

For the Pulse Sequence demo there is an additional loopback of DAC 230_0 and ADC 226_0. It's important that the DACs are on the same tiles.

For the Qubit Emulator demo we used:

* 230_0 – 10 MHz-1 GHz baluns – 226_0
* 230_2 – 1 GHz-4 GHz baluns – 226_2
* 229_0 – 1 GHz-4 GHz baluns – 227_2

226_2 and 229_0 are connected via the emulator.

