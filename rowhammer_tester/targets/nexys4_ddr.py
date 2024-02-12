#!/usr/bin/env python3

from migen import *

from litex_boards.platforms import digilent_nexys4ddr
from litex.build.xilinx.vivado import vivado_build_args, vivado_build_argdict
from litex.soc.integration.builder import Builder
from litex.soc.cores.clock import S7PLL, S7IDELAYCTRL, S7MMCM

from litedram.phy import s7ddrphy

from liteeth.phy.rmii import LiteEthPHYRMII

from rowhammer_tester.targets import common

# CRG ----------------------------------------------------------------------------------------------

class CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.submodules.pll = pll = S7MMCM(speedgrade=-1)
        self.comb += pll.reset.eq(~platform.request("cpu_reset"))
        pll.register_clkin(platform.request("clk100"), 100e6)

        self.clock_domains.cd_sys = ClockDomain()
        pll.create_clkout(self.cd_sys, sys_clk_freq)

        # Etherbone --------------------------------------------------------------------------------
        self.clock_domains.cd_eth = ClockDomain()
        pll.create_clkout(self.cd_eth, 25e6)
        # self.comb += platform.request("eth_ref_clk").eq(self.cd_eth.clk)

        # DDRPHY -----------------------------------------------------------------------------------
        self.clock_domains.cd_sys2x     = ClockDomain(reset_less=True)
        self.clock_domains.cd_sys2x_dqs = ClockDomain(reset_less=True)

        pll.create_clkout(self.cd_sys2x,     2*sys_clk_freq)
        pll.create_clkout(self.cd_sys2x_dqs, 2*sys_clk_freq, phase=90)

        self.clock_domains.cd_clk200 = ClockDomain()
        pll.create_clkout(self.cd_clk200, 200e6)
        self.submodules.idelayctrl = S7IDELAYCTRL(self.cd_clk200)

# SoC ----------------------------------------------------------------------------------------------

class SoC(common.RowHammerSoC):
    def __init__(self, toolchain='vivado', **kwargs): #variant="a7-35", 
        self.toolchain = toolchain
        #self.variant = variant
        super().__init__(**kwargs)

        # # Analyzer ---------------------------------------------------------------------------------
        # analyzer_signals = [
        #     self.sdram.dfii.ext_dfi_sel,
        #     *[p.rddata for p in self.ddrphy.dfi.phases],
        #     *[p.rddata_valid for p in self.ddrphy.dfi.phases],
        #     *[p.rddata_en for p in self.ddrphy.dfi.phases],
        # ]
        # from litescope import LiteScopeAnalyzer
        # self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals,
        #    depth        = 512,
        #    clock_domain = "sys",
        #    csr_csv      = "analyzer.csv")
        # self.add_csr("analyzer")

    def get_platform(self):
        return digilent_nexys4ddr.Platform(toolchain=self.toolchain) #variant=self.variant,

    def get_crg(self):
        return CRG(self.platform, self.sys_clk_freq)

    def get_ddrphy(self):
        return s7ddrphy.A7DDRPHY(self.platform.request("ddram"),
            memtype        = "DDR2",
            nphases        = 2,
            sys_clk_freq   = self.sys_clk_freq)

    def get_sdram_ratio(self):
        return "1:2"

    # def add_host_bridge(self):
    #     # pass
    #     # print("ADDING ETHERBONE")
    #     self.add_uartbone(name="serial", baudrate=115200)
    #     self.ethphy = LiteEthPHYRMII(
    #             clock_pads = self.platform.request("eth_clocks"),
    #             pads       = self.platform.request("eth"))
    #     self.add_csr("ethphy")
    #     self.add_etherbone(
    #         phy          = self.ethphy,
    #         ip_address   = self.ip_address,
    #         mac_address  = self.mac_address,
    #         udp_port     = self.udp_port,
    #         buffer_depth = 256)
        # self.submodules.ethphy = LiteEthPHYRMII(
        #     clock_pads = self.platform.request("eth_clocks"),
        #     pads       = self.platform.request("eth"))
        # self.add_csr("ethphy")
        # self.add_etherbone(
        #     phy         = self.ethphy,
        #     ip_address  = self.ip_address,
        #     mac_address = self.mac_address,
        #     udp_port    = self.udp_port,
        #     buffer_depth=256)

    def add_host_bridge(self):
        self.add_uartbone(name="serial", baudrate=115200)


        # Don't need ethernet, we have usb_fifo
        self.ethphy = LiteEthPHYRMII(
                clock_pads = self.platform.request("eth_clocks"),
                pads       = self.platform.request("eth"))
        self.add_csr("ethphy")
        self.add_etherbone(
            phy         = self.ethphy,
            ip_address  = self.ip_address,
            mac_address = self.mac_address,
            udp_port    = self.udp_port,
            buffer_depth=256)

# Build --------------------------------------------------------------------------------------------

def main():
    parser = common.ArgumentParser(
        description  = "LiteX SoC on Nexys4 DDR",
        sys_clk_freq = '75e6',
        module       = 'MT47H64M16',
    )
    g = parser.add_argument_group(title="nexys4 ddr")
    parser.add(g, "--toolchain", default="vivado", choices=['vivado', 'symbiflow'],
        help="Gateware toolchain to use")
    # parser.add_argument("--load", action="store_true", help="Load fpga onto board")
    # parser.add(g, "--variant", default="a7-35", choices=['a7-35', 'a7-100'], help="FPGA variant")
    vivado_build_args(g)
    args = parser.parse_args()

    soc_kwargs = common.get_soc_kwargs(args)
    soc = SoC(toolchain=args.toolchain, **soc_kwargs)

    target_name = 'nexys4_ddr'
    builder_kwargs = common.get_builder_kwargs(args, target_name=target_name)
    builder = Builder(soc, **builder_kwargs)
    build_kwargs = vivado_build_argdict(args) if not args.sim else {}

    common.run(args, builder, build_kwargs, target_name=target_name)

    # if args.load:
    #     prog = soc.platform.create_programmer()
    #     prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

if __name__ == "__main__":
    main()
