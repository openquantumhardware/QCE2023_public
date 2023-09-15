import numpy as np
from qick.qick import SocIp

class AbsPfbAnalysis(SocIp):
    # Trace parameters.
    STREAM_IN_PORT	= 's_axis'
    STREAM_OUT_PORT = 'm_axis'

    # Flags.
    HAS_ADC         = False
    HAS_DDSCIC      = False
    HAS_DDS_DUAL    = False
    HAS_CIC         = False
    HAS_CHSEL       = False
    HAS_STREAMER    = False
    HAS_DMA         = False
    HAS_KIDSIM      = False

    def configure(self, fs):
        # Channel centers.
        fc = fs/self.dict['N']

        # Channel bandwidth.
        fb = fs/(self.dict['N']/2)

        # Add data into dictionary.
        self.dict['freq'] = {'fs' : fs, 'fc' : fc, 'fb' : fb}
    
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
            elif blocktype == "axis_reorder_iq_v1":
                ((block, port),) = soc.metadata.trace_bus(block, 's_axis')
            elif blocktype == "axis_combiner":
                self.HAS_ADC = True
                # Sanity check: combiner should have 2 slave ports.
                nslave = int(soc.metadata.get_param(block, 'C_NUM_SI_SLOTS'))

                if nslave != 2:
                    raise RuntimeError("Block %s has %d S_AXIS inputs. It should have 2." % (block, nslave))

                # Trace the two interfaces.
                ((block0, port0),) = soc.metadata.trace_bus(block, 'S00_AXIS')
                ((block1, port1),) = soc.metadata.trace_bus(block, 'S01_AXIS')

                # Get ADC and tile.
                tile, adc_ch = self.ports2adc(port0, port1)

                # Fill adc data dictionary.
                id_ = str(tile) + str(adc_ch)
                self.dict['adc'] = {'tile' : tile, 'ch' : adc_ch, 'id' : id_}

                # Keep tracing back.
                block = block0
                port = port0
                break
            else:
                raise RuntimeError("falied to trace port for %s - unrecognized IP block %s" % (self.fullpath, block))

        ########################################################
        ### Forward tracing: should finish on the KIDSIM/DMA ###
        ########################################################
        ((block,port),) = soc.metadata.trace_bus(self.fullpath, self.STREAM_OUT_PORT)

        while True:
            blocktype = soc.metadata.mod2type(block)

            if blocktype == "axi_dma":
                self.HAS_DMA = True

                # Add dma into dictionary.
                self.dict['dma'] = block
                break
            elif blocktype == "axis_kidsim_v3":
                self.HAS_KIDSIM = True

                # Add kidsim into dictionary.
                self.dict['kidsim'] = block
                break
            elif blocktype == "axis_register_slice":
                ((block, port),) = soc.metadata.trace_bus(block, 'M_AXIS')
            elif blocktype == "axis_ddscic_v2":
                self.HAS_DDSCIC = True

                # Add ddscic into dictionary.
                self.dict['ddscic'] = block

                ((block, port),) = soc.metadata.trace_bus(block, 'm_axis')
            elif blocktype == "axis_dds_dual_v1":
                self.HAS_DDS_DUAL = True

                # Add ddscic into dictionary.
                self.dict['dds'] = block
                ((block, port),) = soc.metadata.trace_bus(block, 'm1_axis')
            elif blocktype == "axis_cic_v1":
                self.HAS_CIC = True

                # Add ddscic into dictionary.
                self.dict['cic'] = block
                ((block, port),) = soc.metadata.trace_bus(block, 'm_axis')
            elif blocktype == "axis_chsel_pfb_v2":
                self.HAS_CHSEL = True

                # Add chsel into dictionary.
                self.dict['chsel'] = block

                ((block, port),) = soc.metadata.trace_bus(block, 'm_axis')
            elif blocktype == "axis_streamer_v1":
                self.HAS_STREAMER = True

                # Add streamer into dictionary.
                self.dict['streamer'] = block

                ((block, port),) = soc.metadata.trace_bus(block, 'm_axis')
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

    def freq2ch(self,f):
        # Check if frequency is on -fs/2 .. fs/2.
        if ( -self.dict['freq']['fs']/2 < f < self.dict['freq']['fs']/2):
            k = np.round(f/self.dict['freq']['fc'])

            if k >= 0:
                return int(k)
            else:
                return int (self.dict['N'] + k)

    def ch2freq(self,ch):
        if ch >= self.dict['N']/2:
            ch_ = self.dict['N'] - ch
            return -(ch_*self.dict['freq']['fc'])
        else:
            return ch*self.dict['freq']['fc']

    def qout(self, qout):
        self.qout_reg = qout

class AxisPfbAnalysis(AbsPfbAnalysis):
    """
    AxisPfbAnalysis class
    Supports AxisPfb4x1024V1, AxisPfbaPr4x256V1
    """
    bindto = ['user.org:user:axis_pfb_4x1024_v1:1.0'   ,
              'user.org:user:axis_pfba_pr_4x256_v1:1.0']
    REGISTERS = {'qout_reg' : 0}
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.qout_reg = 0

        # Dictionary.
        self.dict = {}
        self.dict['N'] = int(description['parameters']['N'])

class AbsPfbSynthesis(SocIp):
    # Trace parameters.
    STREAM_IN_PORT	= 's_axis'
    STREAM_OUT_PORT = 'm_axis'

    # Flags.
    HAS_DAC         = False
    HAS_DDS         = False
    HAS_DDS_DUAL    = False
    HAS_KIDSIM      = False

    def configure(self, fs):
        # Channel centers.
        fc = fs/self.dict['N']

        # Channel bandwidth.
        fb = fs/(self.dict['N']/2)

        # Add data into dictionary.
        self.dict['freq'] = {'fs' : fs, 'fc' : fc, 'fb' : fb}
    
    def configure_connections(self, soc):
        self.soc = soc

        #########################################################
        ### Backward tracing: should finish at the DDS/KIDSIM ###
        #########################################################
        ((block,port),) = soc.metadata.trace_bus(self.fullpath, self.STREAM_IN_PORT)

        while True:
            blocktype = soc.metadata.mod2type(block)

            if blocktype == "axis_dds_v3":
                self.HAS_DDS = True

                # Add dds to dictionary.
                self.dict['dds'] = block
                break
            elif blocktype == "axis_dds_dual_v1":
                self.HAS_DDS_DUAL = True

                # Add dds to dictionary.
                self.dict['dds'] = block
                break
            elif blocktype == "axis_kidsim_v3":
                self.HAS_KIDSIM = True

                # Add dds to dictionary.
                self.dict['kidsim'] = block
                break
            elif blocktype == "axis_register_slice":
                ((block, port),) = soc.metadata.trace_bus(block, 'S_AXIS')
            else:
                raise RuntimeError("falied to trace port for %s - unrecognized IP block %s" % (self.fullpath, block))

        #############################################
        ### Forward tracing: should finish on DAC ###
        #############################################
        ((block,port),) = soc.metadata.trace_bus(self.fullpath, self.STREAM_OUT_PORT)

        while True:
            blocktype = soc.metadata.mod2type(block)

            if blocktype == "usp_rf_data_converter":
                self.HAS_DAC = True

                # Get DAC and tile.
                tile, dac_ch = self.port2dac(port)

                # Add dac data into dictionary.
                id_ = str(tile) + str(dac_ch)
                self.dict['dac'] = {'tile' : tile, 'ch' : dac_ch, 'id' : id_}
                break
            elif blocktype == "axis_register_slice":
                ((block, port),) = soc.metadata.trace_bus(block, 'M_AXIS')
            elif blocktype == "axis_clock_converter":
                ((block, port),) = soc.metadata.trace_bus(block, 'M_AXIS')
            else:
                raise RuntimeError("falied to trace port for %s - unrecognized IP block %s" % (self.fullpath, block))

    def port2dac(self, port):
        # This function cheks the port correspond to a DAC.
        # The correspondance is:
        #
        # DAC0, tile 0.
        # s00_axis
        #
        # DAC1, tile 0.
        # s01_axis
        #
        # DAC2, tile 0.
        # s02_axis
        #
        # DAC3, tile 0.
        # s03_axis
        #
        # DAC0, tile 1.
        # s10_axis
        #
        # DAC1, tile 1.
        # s11_axis
        #
        # DAC2, tile 1.
        # s12_axis
        #
        # DAC3, tile 1.
        # s13_axis
        #
        # DAC0, tile 2.
        # s20_axis
        #
        # DAC1, tile 2.
        # s21_axis
        #
        # DAC2, tile 2.
        # s22_axis
        #
        # DAC3, tile 2.
        # s23_axis
        #
        # DAC0, tile 3.
        # s30_axis
        #
        # DAC1, tile 3.
        # s31_axis
        #
        # DAC2, tile 3.
        # s32_axis
        #
        # DAC3, tile 3.
        # s33_axis
        #
        # First value, tile.
        # Second value, dac.
        dac_dict =  {
            '0' :   {
                        '0' : {'port' : 's00'}, 
                        '1' : {'port' : 's01'}, 
                        '2' : {'port' : 's02'}, 
                        '3' : {'port' : 's03'}, 
                    },
            '1' :   {
                        '0' : {'port' : 's10'}, 
                        '1' : {'port' : 's11'}, 
                        '2' : {'port' : 's12'}, 
                        '3' : {'port' : 's13'}, 
                    },
            '2' :   {
                        '0' : {'port' : 's20'}, 
                        '1' : {'port' : 's21'}, 
                        '2' : {'port' : 's22'}, 
                        '3' : {'port' : 's23'}, 
                    },
            '3' :   {
                        '0' : {'port' : 's30'}, 
                        '1' : {'port' : 's31'}, 
                        '2' : {'port' : 's32'}, 
                        '3' : {'port' : 's33'}, 
                    },
                    }
        p_n = port[0:3]

        # Find adc<->port.
        for tile in dac_dict.keys():
            for dac in dac_dict[tile].keys():
                if p_n == dac_dict[tile][dac]['port']:
                    return tile,dac

        # If I got here, dac not found.
        raise RuntimeError("Cannot find correspondance with any DAC for port %s" % (port))


    def freq2ch(self,f):
        # Check if frequency is on -fs/2 .. fs/2.
        if ( -self.dict['freq']['fs']/2 < f < self.dict['freq']['fs']/2):
            k = np.round(f/self.dict['freq']['fc'])

            if k >= 0:
                return int(k)
            else:
                return int (self.dict['N'] + k)

    def ch2freq(self,ch):
        if ch >= self.dict['N']/2:
            ch_ = self.dict['N'] - ch
            return -(ch_*self.dict['freq']['fc'])
        else:
            return ch*self.dict['freq']['fc']

    def qout(self, value):
        self.qout_reg = value

class AxisPfbSynthesis(AbsPfbSynthesis):
    """
    AxisPfbSynthesis class
    Supports AxisPfbSynth4x1024V1, AxisPfbsPr4x256V1
    """
    bindto = ['user.org:user:axis_pfbsynth_4x1024_v1:1.0',
              'user.org:user:axis_pfbs_pr_4x256_v1:1.0'  ]
    REGISTERS = {'qout_reg':0}
    
    def __init__(self, description):
        # Initialize ip
        super().__init__(description)
        
        # Default registers.
        self.qout_reg   = 0

        # Dictionary.
        self.dict = {}
        self.dict['N'] = int(description['parameters']['N'])
        
