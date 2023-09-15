from qick.qick import SocIp
import numpy as np

class AxisDdsCicV2(SocIp):
    bindto = ['user.org:user:axis_ddscic_v2:1.0']
    REGISTERS = {'addr_nchan_reg' : 0, 
                 'addr_pinc_reg'  : 1, 
                 'addr_we_reg'    : 2, 
                 'dds_sync_reg'   : 3, 
                 'dds_outsel_reg' : 4,
                 'cic_rst_reg'    : 5,
                 'cic_d_reg'      : 6, 
                 'qdata_qsel_reg' : 7}
    
    # Decimation range.
    MIN_D = 1
    MAX_D = 250
    
    # Quantization range.
    MIN_Q = 0
    MAX_Q = 24
    
    # Sampling frequency and frequency resolution (Hz).
    FS_DDS = 1000
    DF_DDS = 1
    DF_DDS_MHZ = 1
    
    # DDS bits.
    B_DDS = 16
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.addr_nchan_reg = 0
        self.addr_pinc_reg  = 0
        self.addr_we_reg    = 0
        self.dds_sync_reg   = 1 # Keep syncing DDS.
        self.dds_outsel_reg = 0
        self.cic_rst_reg    = 1 # Keep resetting accumulator.
        self.cic_d_reg      = 4 # Decimate-by-4.
        self.qdata_qsel_reg = 0 # Upper bits for truncation.
        
        # Generics.
        self.L = int(description['parameters']['L'])
        self.NCH = int(description['parameters']['NCH'])
        self.NCH_TOTAL = self.L * self.NCH

        # Set DDS Frequencies to 0.
        for i in range(self.NCH_TOTAL):
            self.set_ddsfreq(ch_id = i)

        # Start DDS.
        self.dds_start()

    def configure(self, fs):
        fs_hz = fs*1000*1000
        self.FS_DDS = fs_hz
        self.DF_DDS = self.FS_DDS/2**self.B_DDS
        self.DF_DDS_MHZ = self.DF_DDS/1000/1000
        
    def dds_start(self):
        self.dds_sync_reg = 0
        self.cic_rst_reg  = 0
        
    def dds_outsel(self, outsel="product"):
        if outsel == "product":
            self.dds_outsel_reg = 0
        elif outsel == "dds":
            self.dds_outsel_reg = 1
        elif outsel == "input":
            self.dds_outsel_reg = 2
            
    def decimate(self, decimate=4):
        # Sanity check.
        if (decimate >= self.MIN_D and decimate <= self.MAX_D):
            self.cic_d_reg = decimate
            
    def qsel(self, value=0):
        # Sanity check.
        if (value >= self.MIN_Q and value <= self.MAX_Q):
            self.qdata_qsel_reg = value
            
    def get_decimate(self):
        return self.cic_d_reg
    
    def decimation(self, value):
        # Sanity check.
        if (value >= self.MIN_D and value <= self.MAX_D):
            # Compute CIC output quantization.
            qsel = self.MAX_Q - np.ceil(3*np.log2(value))
            
            # Set values.
            self.decimate(value)
            self.qsel(qsel)    
    
    def set_ddsfreq(self, ch_id=0, f=0):
        # Sanity check.
        if (ch_id >= 0 and ch_id < self.NCH_TOTAL):
            if (f >= -self.FS_DDS/2 and f < self.FS_DDS/2):
            #if (f >= 0 and f < self.FS_DDS):
                # Compute register value.
                ki = int(round(f/self.DF_DDS))
                
                # Write value into hardware.
                self.addr_nchan_reg = ch_id
                self.addr_pinc_reg = ki
                self.addr_we_reg = 1
                self.addr_we_reg = 0                
        
class AxisCicV1(SocIp):
    bindto = ['user.org:user:axis_cic_v1:1.0']
    REGISTERS = {'cic_rst_reg'    : 0,
                 'cic_d_reg'      : 1, 
                 'qdata_qsel_reg' : 2}
    
    # Decimation range.
    MIN_D = 1
    MAX_D = 250
    
    # Quantization range.
    MIN_Q = 0
    MAX_Q = 24
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.cic_rst_reg    = 1 # Keep resetting accumulator.
        self.cic_d_reg      = 4 # Decimate-by-4.
        self.qdata_qsel_reg = 0 # Upper bits for truncation.
        
        # Generics.
        self.L = int(description['parameters']['L'])
        self.NCH = int(description['parameters']['NCH'])
        self.NCH_TOTAL = self.L * self.NCH

        # Start.
        self.start()

    def start(self):
        self.cic_rst_reg  = 0
        
    def decimate(self, decimate=4):
        # Sanity check.
        if (decimate >= self.MIN_D and decimate <= self.MAX_D):
            self.cic_d_reg = decimate
            
    def qsel(self, value=0):
        # Sanity check.
        if (value >= self.MIN_Q and value <= self.MAX_Q):
            self.qdata_qsel_reg = value
            
    def get_decimate(self):
        return self.cic_d_reg
    
    def decimation(self, value):
        # Sanity check.
        if (value >= self.MIN_D and value <= self.MAX_D):
            # Compute CIC output quantization.
            qsel = self.MAX_Q - np.ceil(3*np.log2(value))
            
            # Set values.
            self.decimate(value)
            self.qsel(qsel)    
    
class AxisDdsV2(SocIp):
    bindto = ['user.org:user:axis_dds_v2:1.0']
    REGISTERS = {'addr_nchan_reg' : 0, 
                 'addr_pinc_reg'  : 1, 
                 'addr_phase_reg' : 2,
                 'addr_gain_reg'  : 3,
                 'addr_cfg_reg'   : 4,
                 'addr_we_reg'    : 5,                  
                 'dds_sync_reg'   : 6}
    
    # Sampling frequency and frequency resolution (Hz).
    FS_DDS      = 1000
    DF_DDS      = 1
    DFI_DDS     = 1
    
    # DDS bits.
    B_DDS       = 16

    # Gain.
    B_GAIN      = 16
    MIN_GAIN    = -1
    MAX_GAIN    = 1

    # Phase.
    MIN_PHI     = 0
    MAX_PHI     = 360
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.addr_nchan_reg = 0;
        self.addr_pinc_reg  = 0;
        self.addr_phase_reg = 0;
        self.addr_gain_reg  = 0;
        self.addr_cfg_reg   = 0; # DDS output.
        self.addr_we_reg    = 0;
        self.dds_sync_reg   = 1; # Sync DDS.

        # Generics
        self.L      = int(description['parameters']['L'])
        self.NCH    = int(description['parameters']['NCH'])
        self.NCH_TOTAL = self.L * self.NCH

        # Initialize DDSs.
        for i in range(self.NCH_TOTAL):
            self.ddscfg(ch = i)

        # Start DDS.
        self.start()
        
    def configure(self, fs):
        fs_hz = fs*1000*1000
        self.FS_DDS     = fs_hz
        self.DF_DDS     = self.FS_DDS/2**self.B_DDS
        self.DFI_DDS    = self.MAX_PHI/2**self.B_DDS

    def start(self):
        self.dds_sync_reg   = 0

    def ddscfg(self, f=0, fi=0, g=0, ch=0, sel="dds"):
        # Sanity check.
        if (ch >= 0 and ch < self.NCH_TOTAL):
            if (f >= -self.FS_DDS/2 and f < self.FS_DDS/2):
                if (fi >= self.MIN_PHI and fi < self.MAX_PHI): 
                    if (g >= self.MIN_GAIN and g < self.MAX_GAIN):
                        # Compute pinc value.
                        ki = int(round(f/self.DF_DDS))

                        # Compute phase value.
                        fik = int(round(fi/self.DFI_DDS))

                        # Compute gain.
                        gi  = g*(2**(self.B_GAIN-1))

                        # Output selection.
                        if sel == "noise":
                            self.addr_cfg_reg = 1
                        else:
                            self.addr_cfg_reg = 0

                        # Write values to hardware.
                        self.addr_nchan_reg = ch
                        self.addr_pinc_reg  = ki
                        self.addr_phase_reg = fik
                        self.addr_gain_reg  = gi
                        self.addr_we_reg    = 1
                        self.addr_we_reg    = 0
                    else:
                        raise ValueError('gain=%f not contained in [%f,%f)'%(g,self.MIN_GAIN,self.MAX_GAIN))
                else:
                    raise ValueError('phase=%f not contained in [%f,%f)'%(fi,self.MIN_PHI,self.MAX_PHI))
            else:
                raise ValueError('frequency=%f not contained in [%f,%f)'%(f,0,self.FS_DDS))
        else:
            raise ValueError('ch=%d not contained in [%d,%d)'%(ch,0,self.NCH_TOTAL))
            
    def alloff(self):
        for ch in np.arange(self.NCH_TOTAL):
            self.ddscfg(g=0, ch=ch)            
            
class AxisDdsV3(SocIp):
    bindto = ['user.org:user:axis_dds_v3:1.0']
    REGISTERS = {'addr_nchan_reg' : 0, 
                 'addr_pinc_reg'  : 1, 
                 'addr_phase_reg' : 2,
                 'addr_gain_reg'  : 3,
                 'addr_cfg_reg'   : 4,
                 'addr_we_reg'    : 5,                  
                 'dds_sync_reg'   : 6}
    
    # Sampling frequency and frequency resolution (Hz).
    FS_DDS      = 1000
    DF_DDS      = 1
    DFI_DDS     = 1
    
    # DDS bits.
    B_DDS       = 16

    # Gain.
    B_GAIN      = 16
    MIN_GAIN    = -1
    MAX_GAIN    = 1

    # Phase.
    MIN_PHI     = 0
    MAX_PHI     = 360
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.addr_nchan_reg = 0;
        self.addr_pinc_reg  = 0;
        self.addr_phase_reg = 0;
        self.addr_gain_reg  = 0;
        self.addr_cfg_reg   = 0; # DDS output.
        self.addr_we_reg    = 0;
        self.dds_sync_reg   = 1; # Sync DDS.

        # Generics
        self.L      = int(description['parameters']['L'])
        self.NCH    = int(description['parameters']['NCH'])
        self.NCH_TOTAL = self.L * self.NCH

        # Initialize DDSs.
        for i in range(self.NCH_TOTAL):
            self.ddscfg(ch = i)

        # Start DDS.
        self.start()
        
    def configure(self, fs):
        fs_hz = fs*1000*1000
        self.FS_DDS     = fs_hz
        self.DF_DDS     = self.FS_DDS/2**self.B_DDS
        self.DFI_DDS    = self.MAX_PHI/2**self.B_DDS

    def start(self):
        self.dds_sync_reg   = 0

    def ddscfg(self, f=0, fi=0, g=0, ch=0, sel="dds"):
        # Sanity check.
        if (ch >= 0 and ch < self.NCH_TOTAL):
            if (f >= -self.FS_DDS/2 and f < self.FS_DDS/2):
                if (fi >= self.MIN_PHI and fi < self.MAX_PHI): 
                    if (g >= self.MIN_GAIN and g < self.MAX_GAIN):
                        # Compute pinc value.
                        ki = int(round(f/self.DF_DDS))

                        # Compute phase value.
                        fik = int(round(fi/self.DFI_DDS))

                        # Compute gain.
                        gi  = g*(2**(self.B_GAIN-1))

                        # Output selection.
                        if sel == "noise":
                            self.addr_cfg_reg = 1
                        else:
                            self.addr_cfg_reg = 0

                        # Write values to hardware.
                        self.addr_nchan_reg = ch
                        self.addr_pinc_reg  = ki
                        self.addr_phase_reg = fik
                        self.addr_gain_reg  = gi
                        self.addr_we_reg    = 1
                        self.addr_we_reg    = 0
                    else:
                        raise ValueError('gain=%f not contained in [%f,%f)'%(g,self.MIN_GAIN,self.MAX_GAIN))
                else:
                    raise ValueError('phase=%f not contained in [%f,%f)'%(fi,self.MIN_PHI,self.MAX_PHI))
            else:
                raise ValueError('frequency=%f not contained in [%f,%f)'%(f,0,self.FS_DDS))
        else:
            raise ValueError('ch=%d not contained in [%d,%d)'%(ch,0,self.NCH_TOTAL))
            
    def alloff(self):
        for ch in np.arange(self.NCH_TOTAL):
            self.ddscfg(g=0, ch=ch)            

class AxisDdsDualV1(SocIp):
    bindto = ['user.org:user:axis_dds_dual_v1:1.0']
    REGISTERS = {'addr_nchan_reg'       : 0, 
                 'addr_pinc_reg'        : 1, 
                 'addr_phase_reg'       : 2,
                 'addr_dds_gain_reg'    : 3,
                 'addr_comp_gain_reg'   : 4,
                 'addr_cfg_reg'         : 5,
                 'addr_we_reg'          : 6,                  
                 'dds_sync_reg'         : 7}
    
    # Sampling frequency and frequency resolution (Hz).
    FS_DDS      = 1000
    DF_DDS      = 1
    DFI_DDS     = 1
    
    # DDS bits.
    B_DDS       = 32

    # Gain.
    B_GAIN      = 16
    MIN_GAIN    = -1
    MAX_GAIN    = 1

    # Phase.
    MIN_PHI     = 0
    MAX_PHI     = 360
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.addr_nchan_reg     = 0;
        self.addr_pinc_reg      = 0;
        self.addr_phase_reg     = 0;
        self.addr_dds_gain_reg  = 0;
        self.addr_comp_gain_reg = 0;
        self.addr_cfg_reg       = 0; # Down-coverted and compensated output.
        self.addr_we_reg        = 0;
        self.dds_sync_reg       = 1; # Sync DDS.

        # Default sel.
        self.sel_default = "product"

        # Generics
        self.L      = int(description['parameters']['L'])
        self.NCH    = int(description['parameters']['NCH'])
        self.NCH_TOTAL = self.L * self.NCH

        # Initialize DDSs.
        for i in range(self.NCH_TOTAL):
            self.ddscfg(ch = i)

        # Start DDS.
        self.start()
        
    def configure(self, fs):
        fs_hz = fs*1000*1000
        self.FS_DDS     = fs_hz
        self.DF_DDS     = self.FS_DDS/2**self.B_DDS
        self.DFI_DDS    = self.MAX_PHI/2**self.B_DDS

    def start(self):
        self.dds_sync_reg   = 0

    def dds_outsel(self, sel="product"):
        # Set default outsel (for compatibility with DDS+CIC).
        self.sel_default = sel

    def ddscfg(self, f=0, fi=0, g=0, cg=0, ch=0, comp=False):
        # Real/Imaginary part of compensation gain.
        cg_i = np.real(cg)
        cg_q = np.imag(cg)

        # Sanity check.
        if (ch >= 0 and ch < self.NCH_TOTAL):
            if (f >= -self.FS_DDS/2 and f < self.FS_DDS/2):
                if (fi >= self.MIN_PHI and fi < self.MAX_PHI): 
                    if (g >= self.MIN_GAIN and g < self.MAX_GAIN):
                        if (cg_i >= self.MIN_GAIN and cg_i < self.MAX_GAIN):
                            if (cg_q >= self.MIN_GAIN and cg_q < self.MAX_GAIN):
                                # Compute pinc value.
                                ki = int(round(f/self.DF_DDS))

                                # Compute phase value.
                                fik = int(round(fi/self.DFI_DDS))

                                # Compute gain.
                                gi  = g*(2**(self.B_GAIN-1))

                                # Compute compensation gain.
                                cg_i_int = cg_i*(2**(self.B_GAIN-1))
                                cg_q_int = cg_q*(2**(self.B_GAIN-1))
                                cg_int = cg_i_int + (2**self.B_GAIN)*cg_q_int

                                # Output selection.
                                if self.sel_default == "product":
                                    cfg = 0
                                elif self.sel_default == "dds":
                                    cfg = 1
                                elif self.sel_default == "input":
                                    cfg = 2
                                else:
                                    cfg = 3 # 0 value.

                                # Compensation.
                                if not comp:
                                    cfg += 4

                                self.addr_cfg_reg = 0


                                # Write values to hardware.
                                self.addr_nchan_reg     = ch
                                self.addr_pinc_reg      = ki
                                self.addr_phase_reg     = fik
                                self.addr_dds_gain_reg  = gi
                                self.addr_comp_gain_reg = cg_int
                                self.addr_cfg_reg       = cfg
                                self.addr_we_reg    = 1
                                self.addr_we_reg    = 0
                    else:
                        raise ValueError('gain=%f not contained in [%f,%f)'%(g,self.MIN_GAIN,self.MAX_GAIN))
                else:
                    raise ValueError('phase=%f not contained in [%f,%f)'%(fi,self.MIN_PHI,self.MAX_PHI))
            else:
                raise ValueError('frequency=%f not contained in [%f,%f)'%(f,0,self.FS_DDS))
        else:
            raise ValueError('ch=%d not contained in [%d,%d)'%(ch,0,self.NCH_TOTAL))
            
    def alloff(self):
        for ch in np.arange(self.NCH_TOTAL):
            self.ddscfg(ch=ch) # WIll zero-out output and down-convert with 0 freq.

