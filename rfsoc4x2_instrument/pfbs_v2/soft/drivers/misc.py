import numpy as np
from pynq.buffer import allocate
from .ip import SocIp
import time

class MrBufferEt(SocIp):
    # Registers.
    # DW_CAPTURE_REG
    # * 0 : Capture disabled.
    # * 1 : Capture enabled (capture started by external trigger).
    #
    # DR_START_REG
    # * 0 : don't send.
    # * 1 : start sending data.
    #
    # DW_CAPTURE_REG needs to be de-asserted and asserted again to allow a new capture.
    # DR_START_REG needs to be de-assereted and asserted again to allow a new transfer.
    #
    bindto = ['user.org:user:mr_buffer_et:1.0']
    REGISTERS = {'dw_capture_reg': 0, 'dr_start_reg': 1}

    # Tracing ports.
    STREAM_IN_PORT = "s00_axis"
    STREAM_OUT_PORT = "m00_axis"

    # Flags.
    HAS_ADC     = False
    HAS_SWITCH  = False
    HAS_DMA     = False

    def __init__(self, description):
        # Init IP.
        super().__init__(description)

        # Default registers.
        self.dw_capture_reg = 0
        self.dr_start_reg = 0

        # Dictionary.
        self.dict = {}

        # Generics.
        self.dict['B']  = int(description['parameters']['B'])
        self.dict['N']  = int(description['parameters']['N'])
        self.dict['NM'] = int(description['parameters']['NM'])

        # Maximum number of samples
        self.dict['MAX_LENGTH'] = 2**self.dict['N'] * self.dict['NM']

        # Preallocate memory buffers for DMA transfers.
        self.buff = allocate(shape=self.dict['MAX_LENGTH'], dtype=np.int16)

    def configure_connections(self, soc):
        self.soc = soc

        ##################################################
        ### Backward tracing: should finish at the ADC ###
        ##################################################
        ((block,port),) = soc.metadata.trace_bus(self.fullpath, self.STREAM_IN_PORT)

        while True:
            blocktype = soc.metadata.mod2type(block)

            if blocktype == "usp_rf_data_converter":
                if not self.HAS_ADC:
                    self.HAS_ADC = True

                    # Get ADC and tile.
                    tile, adc_ch = self.ports2adc(port, None)

                    # Fill adc data dictionary.
                    id_ = str(tile) + str(adc_ch)
                    self.dict['adc'] = {'tile' : tile, 'ch' : adc_ch, 'id' : id_}
                break
            elif blocktype == "axis_register_slice":
                ((block, port),) = soc.metadata.trace_bus(block, 'S_AXIS')
            else:
                raise RuntimeError("falied to trace port for %s - unrecognized IP block %s" % (self.fullpath, block))

        #################################################
        ### Forward tracing: should finish on the DMA ###
        #################################################
        ((block,port),) = soc.metadata.trace_bus(self.fullpath, self.STREAM_OUT_PORT)

        while True:
            blocktype = soc.metadata.mod2type(block)

            if blocktype == "axi_dma":
                self.HAS_DMA = True

                # Add dma into dictionary.
                self.dict['dma'] = block
                break
            elif blocktype == "axis_switch":
                self.HAS_SWITCH = True

                # Get switch channel.
                ch = int(port[1:3])

                # Add switch into dictionary.
                self.dict['switch']     = block
                self.dict['switch_ch']  = ch

                ((block, port),) = soc.metadata.trace_bus(block, 'M00_AXIS')
            else:
                raise RuntimeError("falied to trace port for %s - unrecognized IP block %s" % (self.fullpath, block))

    def ports2adc(self, port0, port1):
        # This function cheks the given ports correspond to the same ADC.
        # The correspondance is (IQ mode):
        #
        # ADC0, tile 0.
        # m00_axis: I
        # m01_axis: Q
        #
        # ADC1, tile 0.
        # m02_axis: I
        # m03_axis: Q
        #
        # ADC0, tile 1.
        # m10_axis: I
        # m11_axis: Q
        #
        # ADC1, tile 1.
        # m12_axis: I
        # m13_axis: Q
        #
        # ADC0, tile 2.
        # m20_axis: I
        # m21_axis: Q
        #
        # ADC1, tile 2.
        # m22_axis: I
        # m23_axis: Q
        #
        # ADC0, tile 3.
        # m30_axis: I
        # m31_axis: Q
        #
        # ADC1, tile 3.
        # m32_axis: I
        # m33_axis: Q
        adc_dict = {
            '0' :   {
                        '0' : {'port 0' : 'm00', 'port 1' : 'm01'}, 
                        '1' : {'port 0' : 'm02', 'port 1' : 'm03'}, 
                    },
            '1' :   {
                        '0' : {'port 0' : 'm10', 'port 1' : 'm11'}, 
                        '1' : {'port 0' : 'm12', 'port 1' : 'm13'}, 
                    },
            '2' :   {
                        '0' : {'port 0' : 'm20', 'port 1' : 'm21'}, 
                        '1' : {'port 0' : 'm22', 'port 1' : 'm23'}, 
                    },
            '3' :   {
                        '0' : {'port 0' : 'm30', 'port 1' : 'm31'}, 
                        '1' : {'port 0' : 'm32', 'port 1' : 'm33'}, 
                    },
                    }

        p0_n = port0[0:3]

        # Find adc<->port.
        # IQ on same port.
        if port1 is None:
            tile = p0_n[1]
            adc  = p0_n[2]
            return tile,adc

        # IQ on different ports.
        else:
            p1_n = port1[0:3]

            # IQ on different ports.
            for tile in adc_dict.keys():
                for adc in adc_dict[tile].keys():
                    # First possibility.
                    if p0_n == adc_dict[tile][adc]['port 0']:
                        if p1_n == adc_dict[tile][adc]['port 1']:
                            return tile,adc
                    # Second possibility.
                    if p1_n == adc_dict[tile][adc]['port 0']:
                        if p0_n == adc_dict[tile][adc]['port 1']:
                            return tile,adc

        # If I got here, adc not found.
        raise RuntimeError("Cannot find correspondance with any ADC for ports %s,%s" % (port0,port1))

    def configure(self, dma, switch):
        self.dma    = dma
        self.switch = switch

    def capture(self):
        self.dw_capture_reg = 1
        time.sleep(0.1)
        self.dw_capture_reg = 0

    def transfer(self):
        # Set switch channel.
        if self.HAS_SWITCH:
            self.switch.sel(slv = self.dict['switch_ch'])
            
        # Start send data mode.
        self.dr_start_reg = 1

        # DMA data.
        buff = self.buff
        self.dma.recvchannel.transfer(buff)
        self.dma.recvchannel.wait()

        # Stop send data mode.
        self.dr_start_reg = 0

        # Format:
        dataI = buff
        dataI = dataI.astype(np.int16)

        return buff

    def get_data(self):
        # Capture data.
        self.capture()
        
        # Transfer data.
        return self.transfer()

    def enable(self):
        self.dw_capture_reg = 1

    def disable(self):
        self.dw_capture_reg = 0

class AxisSwitch(SocIp):
    """
    AxisSwitch class to control Xilinx AXI-Stream switch IP

    :param nslave: Number of slave interfaces
    :type nslave: int
    :param nmaster: Number of master interfaces
    :type nmaster: int
    """
    bindto = ['xilinx.com:ip:axis_switch:1.1']
    REGISTERS = {'ctrl': 0x0, 'mix_mux': 0x040}

    def __init__(self, description):
        """
        Constructor method
        """
        super().__init__(description)

        # Number of slave interfaces.
        self.NSL = int(description['parameters']['NUM_SI'])
        # Number of master interfaces.
        self.NMI = int(description['parameters']['NUM_MI'])

        # Init axis_switch.
        self.ctrl = 0
        self.disable_ports()

    def disable_ports(self):
        """
        Disables ports
        """
        for ii in range(self.NMI):
            offset = self.REGISTERS['mix_mux'] + 4*ii
            self.write(offset, 0x80000000)

    def sel(self, mst=0, slv=0):
        """
        Digitally connects a master interface with a slave interface

        :param mst: Master interface
        :type mst: int
        :param slv: Slave interface
        :type slv: int
        """
        # Sanity check.
        if slv > self.NSL-1:
            print("%s: Slave number %d does not exist in block." %
                  __class__.__name__)
            return
        if mst > self.NMI-1:
            print("%s: Master number %d does not exist in block." %
                  __class__.__name__)
            return

        # Disable register update.
        self.ctrl = 0

        # Disable all MI ports.
        self.disable_ports()

        # MI[mst] -> SI[slv]
        offset = self.REGISTERS['mix_mux'] + 4*mst
        self.write(offset, slv)

        # Enable register update.
        self.ctrl = 2


class AxisChSelPfbV2(SocIp):
    bindto = ['user.org:user:axis_chsel_pfb_v2:1.0']
    REGISTERS = {   'start_reg' : 0, 
                    'addr_reg'  : 1,
                    'data_reg'  : 2,
                    'we_reg'    : 3}
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Generics.
        self.B      = int(description['parameters']['B'])
        self.L      = int(description['parameters']['L'])        
        self.NCH    = int(description['parameters']['NCH'])        

        # Number of transactions per frame.
        self.NT     = self.NCH//self.L

        # Numbef of memory locations (32 bits per word).
        self.NM     = self.NT//32

        # Dictionary for enabled transactions and channels.
        self.dict = {}
        self.dict['addr'] = [0]*self.NM
        self.dict['tran'] = []
        self.dict['chan'] = []

        # Default registers.
        self.start_reg  = 0
        self.we_reg     = 0
        
        # Mask all channels.
        self.alloff()
        
        # Start block.
        self.start()

    def alloff(self):
        # All bits to 0.
        self.data_reg = 0
        
        for i in np.arange(self.NM):
            # Address.
            self.addr_reg = i

            # WE pulse.
            self.we_reg = 1
            self.we_reg = 0

        # Update dictionary.
        self.dict['addr'] = [0]*self.NM
        self.dict['tran'] = [] 
        self.dict['chan'] = [] 
    
    def stop(self):
        self.start_reg = 0

    def start(self):
        self.start_reg = 1

    def tran2channels(self, tran):
        # Sanity check.
        if tran < self.NT:
            return np.arange(tran*self.L, (tran+1)*self.L)
        else:
            raise ValueError("%s: transaction should be within [0,%d]" % (self.fullpath, self.NT-1))
        
    @property
    def enabled_channels(self):
        if len(self.dict['chan']) > 0:
            self.dict['chan'].sort()
            return self.dict['chan'].astype(int)
        else:
            return self.dict['chan']

    def set(self, ch, single=True, verbose=False):
        # Sanity check.
        if ch < 0 or ch >= self.NCH:
            raise ValueError("%s: channel must be within [0,%d]" %(self.fullpath, self.NCH-1))
        else:
            if verbose:
                print("{}: channel = {}".format(self.fullpath, ch))

            # Is channel already enabled?
            if ch not in self.dict['chan']:
                # Need to mask previously un-masked channels?
                if single:
                    self.alloff()

                    if verbose:
                        print("{}: masking previously enabled channels.".format(self.fullpath))

                # Transaction number and bit index.
                ntran, addr, bit = self.ch2tran(ch)

                if verbose:
                    print("{}: ch = {}, ntran = {}, addr = {}, bit = {}".format(self.fullpath, ch, ntran, addr, bit))

                # Enable neighbors.
                self.dict['chan'] = np.append(self.dict['chan'], self.tran2channels(ntran))

                # Enable transaction.
                self.dict['tran'] = np.append(self.dict['tran'], ntran)

                # Data Mask.
                data = self.dict['addr'][addr] + 2**bit
                if verbose:
                    print("{}: Original Mask: {}, Updated Mask: {}".format(self.fullpath, self.dict['addr'][addr], data))
                self.dict['addr'][addr] = data
            
                # Write Value.
                self.addr_reg = addr
                self.data_reg = data
                self.we_reg = 1
                self.we_reg = 0
            
    def set_single(self,ch):
        self.alloff()
        self.set(ch)
            
    def ch2tran(self,ch):
        # Transaction number.
        ntran = ch//self.L

        # Mask Register Address (each is 32-bit).
        addr = ntran//32
        
        # Bit.
        bit = ntran%32
        
        return ntran,addr, bit
    
    def ch2idx(self,ch):
        return np.mod(ch,self.L)

class AxisChSelPfbV3(SocIp):
    bindto = ['user.org:user:axis_chsel_pfb_v3:1.0']
    REGISTERS = {   'start_reg' : 0, 
                    'punct_reg' : 1}
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Generics.
        self.B      = int(description['parameters']['B'])
        self.L      = int(description['parameters']['L'])        
        self.NCH    = int(description['parameters']['NCH'])        

        # Number of transactions per frame.
        self.NT     = self.NCH//self.L

        # Dictionary for enabled transactions and channels.
        self.dict = {}
        self.dict['punct'] = 0
        self.dict['tran']  = []
        self.dict['chan']  = []

        # Default registers.
        self.start_reg  = 0
        self.punct_reg  = 0
        
        # Mask all channels.
        self.alloff()
        
        # Start block.
        self.start()

    def alloff(self):
        # All bits to 0.
        self.punct_reg = 0
        
        # Update dictionary.
        self.dict['punct'] = 0
        self.dict['tran']  = [] 
        self.dict['chan']  = [] 
    
    def stop(self):
        self.start_reg = 0

    def start(self):
        self.start_reg = 1

    def tran2channels(self, tran):
        # Sanity check.
        if tran < self.NT:
            return np.arange(tran*self.L, (tran+1)*self.L)
        else:
            raise ValueError("%s: transaction should be within [0,%d]" % (self.fullpath, self.NT-1))
        
    @property
    def enabled_channels(self):
        if len(self.dict['chan']) > 0:
            self.dict['chan'].sort()
            return self.dict['chan'].astype(int)
        else:
            return self.dict['chan']

    def set(self, ch, single=True, verbose=False):
        # Sanity check.
        if ch < 0 or ch >= self.NCH:
            raise ValueError("%s: channel must be within [0,%d]" %(self.fullpath, self.NCH-1))
        else:
            if verbose:
                print("{}: channel = {}".format(self.fullpath, ch))

            # Is channel already enabled?
            if ch not in self.dict['chan']:
                # Need to mask previously un-masked channels?
                if single:
                    self.alloff()

                    if verbose:
                        print("{}: masking previously enabled channels.".format(self.fullpath))

                # Transaction number and bit index.
                ntran, bit = self.ch2tran(ch)

                if verbose:
                    print("{}: ch = {}, ntran = {}, bit = {}".format(self.fullpath, ch, ntran, bit))

                # Enable neighbors.
                self.dict['chan'] = np.append(self.dict['chan'], self.tran2channels(ntran))

                # Enable transaction.
                self.dict['tran'] = np.append(self.dict['tran'], ntran)

                # Data Mask.
                data = self.dict['punct'] + 2**bit
                if verbose:
                    print("{}: Original Mask: {}, Updated Mask: {}".format(self.fullpath, self.dict['punct'], data))
                self.dict['punct'] = data
            
                # Write Value.
                self.punct_reg = data
                self.stop()
                self.start()
            
    def set_single(self,ch):
        self.alloff()
        self.set(ch)
            
    def ch2tran(self,ch):
        # Transaction number.
        ntran = ch//self.L

        # Bit.
        bit = ntran%32
        
        return ntran, bit
    
    def ch2idx(self,ch):
        return np.mod(ch,self.L)

class AxisStreamerV1(SocIp):
    # AXIS_Streamer V1 registers.
    # START_REG
    # * 0 : stop.
    # * 1 : start.
    #
    # NSAMP_REG : number of samples per transaction (for TLAST generation).
    bindto = ['user.org:user:axis_streamer_v1:1.0']
    REGISTERS = {'start_reg' : 0, 'nsamp_reg' : 1}
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.start_reg = 0
        self.nsamp_reg = 0
        
        # Generics.
        self.BDATA  = int(description['parameters']['BDATA'])
        self.BUSER  = int(description['parameters']['BUSER'])        
        self.BAXIS  = int(description['parameters']['BAXIS'])
        
        # Number of samples per AXIS transaction (buffer uses 16 bit integer).
        self.NS_TR  = int(self.BAXIS/16)
        
        # Number of data samples per transaction.
        self.NS = int(self.NS_TR/2)
        
        # Number of index samples per transaction.
        self.NI = 1
        
        # Number of total samples per transaction.
        self.NS_NI = self.NS + self.NI
        
    def configure(self,axi_dma):
        self.dma = axi_dma
    
    def stop(self):
        self.start_reg = 0

    def start(self):
        self.start_reg = 1

    def set(self, nsamp=100):
        # Configure parameters.
        self.nsamp_reg  = nsamp
        nbuf = nsamp*self.NS_TR
        self.buff = allocate(shape=(nbuf,), dtype=np.int16)
        
        # Update register value.
        self.stop()
        self.start()
        
    def transfer_raw(self):
        # DMA data.
        self.dma.recvchannel.transfer(self.buff)
        self.dma.recvchannel.wait()   
        
        return self.buff

    def transfer(self,nt=1):
        # Data structure:
        # First dimention: number of dma transfers.
        # Second dimension: number of streamer transactions.
        # Third dimension: Number of I + Number of Q + Index (17 samples, 16-bit each).
        data = np.zeros((nt,self.nsamp_reg,self.NS_NI))
        
        for i in np.arange(nt):
        
            # DMA data.
            self.dma.recvchannel.transfer(self.buff)
            self.dma.recvchannel.wait()
                
            # Data format:
            # Each streamer transaction is 512 bits. It contains 8 samples (32-bit each) plus 1 sample (16-bit) for TUSER.
            # The upper 15 samples are filled with zeros.        
            data[i,:,:] = self.buff.reshape((self.nsamp_reg, -1))[:,:self.NS_NI]
            
        return data
    
    def get_data(self,nt=1,idx=0):
        # nt: number of dma transfers.
        # idx: from 0..7, index of channel.
        
        # Get data.
        packets = self.transfer(nt=nt)
        
        # Number of samples per transfer.
        ns = len(packets[0])
        
        # Format data.
        data_iq = packets[:,:,:16].reshape((-1,16)).T
        xi,xq = data_iq[2*idx:2*idx+2]        
                
        return [xi,xq]

    def get_data_all(self, verbose=False):
        # Get packets.
        packets = self.transfer()

        # Format data.
        data = {'raw' : [], 'idx' : [], 'samples' : {}}

        # Raw packets.
        data['raw'] = packets[:,:,:self.NS].reshape((-1,self.NS)).T

        # Active transactions.
        data['idx']     = packets[:,:,-1].reshape(-1).astype(int)

        # Group samples per transaction index.
        unique_idx = np.unique(data['idx'])
        for i in unique_idx:
            idx = np.argwhere(data['idx'] == i).reshape(-1)
            data['samples'][i] = data['raw'][:,idx]

        return data


    def format_data(self, data):
        unique_idx = np.unique(data['idx'])

        for i in unique_idx:
            idx = np.argwhere(data['idx'] == i).reshape(-1)
            samples[i] = data['samples'][:,idx]

        return samples

    async def transfer_async(self):
        # DMA data.
        self.dma.recvchannel.transfer(self.buff)
        await self.dma.recvchannel.wait_async()

        # Format data.
        data = self.buff & 0xFFFFF;
        indx = (self.buff >> 24) & 0xFF;

        return [indx,data]

class AxisKidsimV3(SocIp):
    bindto = ['user.org:user:axis_kidsim_v3:1.0']
    REGISTERS = {'dds_bval_reg' : 0, 
                 'dds_slope_reg': 1, 
                 'dds_steps_reg': 2, 
                 'dds_wait_reg' : 3, 
                 'dds_freq_reg' : 4, 
                 'iir_c0_reg'   : 5, 
                 'iir_c1_reg'   : 6, 
                 'iir_g_reg'    : 7, 
                 'outsel_reg'   : 8, 
                 'punct_id_reg' : 9, 
                 'addr_reg'     : 10, 
                 'we_reg'       : 11}
    
    # Sampling frequency and frequency resolution (Hz).
    FS_DDS = 1000
    DF_DDS = 1
    
    # DDS bits.
    B_DDS = 16

    # Coefficient/gain bits.
    B_COEF = 16
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.we_reg = 0 # Don't write.
        
        # Generics.
        self.L      = int(description['parameters']['L'])
        self.NCH    = 256
        self.NPUNCT = int(self.NCH/self.L)
        
    def configure(self, fs):
        fs_hz = fs*1000*1000
        self.FS_DDS = fs_hz
        self.DF_DDS = self.FS_DDS/2**self.B_DDS
        
    def set_registers(self, dds_bval, dds_slope, dds_steps, dds_wait, dds_freq, iir_c0, iir_c1, iir_g, outsel, punct_id, addr):
        self.dds_bval_reg  = dds_bval
        self.dds_slope_reg = dds_slope
        self.dds_steps_reg = dds_steps
        self.dds_wait_reg  = dds_wait
        self.dds_freq_reg  = dds_freq
        self.iir_c0_reg    = iir_c0
        self.iir_c1_reg    = iir_c1
        self.iir_g_reg     = iir_g
        self.outsel_reg    = outsel
        self.punct_id_reg  = punct_id
        self.addr_reg      = addr
        
        # Write enable pulse.
        self.we_reg     = 1
        self.we_reg     = 0
        
    
    def set_resonator(self, config, verbose = False):
        self.set_resonator_config(config, verbose)
        self.set_resonator_regs(config, verbose)
        
    def set_resonator_config(self, config, verbose = False):
        # Check if sweep_freq is defined.
        if 'sweep_freq' not in config.keys():
            config['sweep_freq'] = 0.9

        # Check if sweep_time is defined.
        if 'sweep_time' not in config.keys():
            config['sweep_time'] = 100

        # Check if iir_c0 is defined.
        if 'iir_c0' not in config.keys():
            config['iir_c0'] = 0.99

        # Check if iir_c1 is defined.
        if 'iir_c1' not in config.keys():
            config['iir_c1'] = 0.8

        # Gain.
        config['iir_g'] = (1+config['iir_c1'])/(1+config['iir_c0']);

        # Check if sel is defined.
        if 'sel' not in config.keys():
            config['sel'] = 'resonator'

        # Compute PFB Channel from frequency specification.
        if 'channel' not in config.keys():
            config['channel'] = 0

        # Compute DDS frequency.
        if 'dds_freq' not in config.keys():
            config['dds_freq'] = 0

        # Compute Lane number from PFB channel specification.
        config['lane'] = np.mod(config['channel'], self.L)

        # KIDSIM puncuring index.
        config['punct_id'] = int(np.floor(config['channel']/self.L))

        # Sampling frequency of DDSs.
        fs = self.FS_DDS/1e6
        ts = 1/fs

        #  Check if dds_wait is defined.
        if 'dds_wait' not in config.keys():
            config['dds_wait'] = 1

        # Number of steps.
        config['nstep'] = int(config['sweep_time']/((config['dds_wait']+1)*ts))
        
        # Sanity check (slope = 0).
        config['dds_bval_reg'] = int(round(config['sweep_freq']*1e6/self.DF_DDS))
        config['dds_slope_reg'] = int(round(config['dds_bval_reg']/config['nstep']))
        if (config['dds_slope_reg'] < 1):
            config['dds_slope_reg'] = 1
            config['nstep'] = config['dds_bval_reg']
            config['sweep_time'] = config['nstep']*((config['dds_wait']+1)*ts)
            print('{}: Updated sweep_time to {} us. Try increasing dds_wait.'
                  .format(self.__class__.__name__, config['sweep_time']))

        if verbose:
            print('{}: sel        = {}'.format(self.__class__.__name__,config['sel']))
            print('{}: channel    = {}'.format(self.__class__.__name__,config['channel']))
            print('{}: lane       = {}'.format(self.__class__.__name__,config['lane']))
            print('{}: punct_id   = {}'.format(self.__class__.__name__,config['punct_id']))
            print('{}: iir_c0     = {}'.format(self.__class__.__name__,config['iir_c0']))
            print('{}: iir_c1     = {}'.format(self.__class__.__name__,config['iir_c1']))
            print('{}: iir_g      = {}'.format(self.__class__.__name__,config['iir_g']))
            print('{}: dds_freq   = {}'.format(self.__class__.__name__,config['dds_freq']))
            print('{}: dds_wait   = {}'.format(self.__class__.__name__,config['dds_wait']))
            print('{}: sweep_freq = {}'.format(self.__class__.__name__,config['sweep_freq']))
            print('{}: sweep_time = {}'.format(self.__class__.__name__,config['sweep_time']))
            print('{}: nstep      = {}'.format(self.__class__.__name__,config['nstep']))
    
    def set_resonator_regs(self, config, verbose = False):
        # DDS Section Registers.
        dds_bval_reg  = config['dds_bval_reg']
        dds_slope_reg = config['dds_slope_reg']
        dds_steps_reg = config['nstep']
        dds_wait_reg  = config['dds_wait']
        dds_freq_reg  = int(round(config['dds_freq']*1e6/self.DF_DDS))

        if verbose:
            print('freq = {}, bval = {}, slope = {}, steps = {}, wait = {}'
                  .format(dds_freq_reg,dds_bval_reg,dds_slope_reg,dds_steps_reg,dds_wait_reg))

        # IIR Section Registers.
        iir_c0_reg = int(round(config['iir_c0']*(2**(self.B_COEF-1))))
        iir_c1_reg = int(round(config['iir_c1']*(2**(self.B_COEF-1))))
        iir_g_reg  = int(round(config['iir_g' ]*(2**(self.B_COEF-1))))

        if verbose:
            print('c0 = {}, c1 = {}, g = {}'
                  .format(iir_c0_reg, iir_c1_reg, iir_g_reg))

        # Output Section Registers.
        if config['sel'] == "resonator":
            outsel_reg = 0
        elif config['sel'] == "dds":
            outsel_reg = 1
        elif config['sel'] == "input":
            outsel_reg = 2
        else:
            outsel_reg = 3

        punct_id_reg = config['punct_id']
        addr_reg     = config['lane']

        if verbose:
            print('sel = {}, punct_id = {}, addr = {}'
                  .format(outsel_reg, punct_id_reg, addr_reg))

        # Set Registers.
        self.set_registers(
            dds_bval_reg ,
            dds_slope_reg,
            dds_steps_reg,
            dds_wait_reg ,
            dds_freq_reg ,
            iir_c0_reg   ,
            iir_c1_reg   ,
            iir_g_reg    ,
            outsel_reg   ,
            punct_id_reg ,
            addr_reg     )                        
        

    def setall(self, config, verbose = False):
        # Build configuration dictionary.
        self.set_resonator_config(config)
        
        # Set all resonators (L) to the same configuration.
        for i in range(self.L):
            # Overwrite lane.
            config['lane'] = i

            # Write values into hardware.
            self.set_resonator_regs(config, verbose)

class AxisFilterV1(SocIp):
    bindto = ['user.org:user:axis_filter_v1:1.0']
    REGISTERS = {'punct0_reg': 0, 
                 'punct1_reg': 1, 
                 'punct2_reg': 2, 
                 'punct3_reg': 3, 
                 'punct4_reg': 4, 
                 'punct5_reg': 5, 
                 'punct6_reg': 6, 
                 'punct7_reg': 7}
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.we_reg = 0 # Don't write.
        
        # Generics.
        self.B = int(description['parameters']['B'])
        self.L = int(description['parameters']['L'])
        self.N = int(description['parameters']['N'])

        # Dictionary to maintain enabled channels.
        self.dict = {}
        self.dict['channels'] = []
        self.dict['lanes'] = [0]*self.L

        # Enable all channels.
        self.allon()

    def write(self):
        # Write registers.
        for i,val in enumerate(self.dict['lanes']):
            setattr(self, "punct%d_reg" % (i), np.uint32(val))

    def alloff(self):
        # all channels off.
        self.dict['channels'] = []
        self.dict['lanes'] = [0]*self.L

        # Write registers.
        self.write()

    def allon(self):
        # all channels on.
        self.dict['channels'] = np.arange(self.N)

        # Puncture all channels.
        val = int(2**(self.N/self.L)-1)
        self.dict['lanes'] = [val]*self.L

        # Write registers.
        self.write()

    def set_channel(self, config, verbose = False):
        # Sanity check.
        if 'channel' in config.keys():
            if (self.N <= config['channel'] < 0):
                raise ValueError("%s: channel must be within [0,%d]" % (self.fullpath, self.N-1))
        else:
            raise ValueError("%s: channel must be defined" % (self.fullpath))

        # Check if channel is already active.
        if config['channel'] in self.dict['channels']:
            if verbose:
                print("{}: channel {} is already active.".format(self.fullpath,config['channel']))
        else:
            # Add channel to active list.
            self.dict['channels'].append(config['channel'])

            # Compute Lane number from PFB channel specification.
            lane = np.mod(config['channel'], self.L)

            # Filter puncuring index.
            punct_id = int(np.floor(config['channel']/self.L))

            # Update structure.
            self.dict['lanes'][lane] = self.dict['lanes'][lane] + 2**punct_id

            if verbose:
                print('{}: channel      = {}'.format(self.__class__.__name__, config['channel']))
                print('{}: lane         = {}'.format(self.__class__.__name__, lane))
                print('{}: punct_id     = {}'.format(self.__class__.__name__, punct_id))
                print('{}: punct{}_reg  = {}'.format(self.__class__.__name__, lane, self.dict['lanes'][lane]))

            # Write registers.
            self.write()

