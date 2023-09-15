import numpy as np
from pynq.buffer import allocate
from qick.qick import SocIp

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

        # Check if nstep is defined.
        if 'nstep' in config.keys():
            config['dds_wait'] = int(config['sweep_time']/(config['nstep']*ts)) - 1
        else:
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

