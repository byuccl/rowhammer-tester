#!/usr/bin/env python3

import math

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.xilinx.vivado import vivado_build_args, vivado_build_argdict
from litex.soc.integration.builder import Builder
from litex.soc.cores.bitbang import I2CMaster
from litex.soc.cores.clock import S7PLL, S7MMCM, S7IDELAYCTRL

from litex_boards.platforms import antmicro_ddr5_tester
from litedram.phy import ddr5
from liteeth.phy import LiteEthS7PHYRGMII

from rowhammer_tester.targets import common

# CRG ----------------------------------------------------------------------------------------------

class CRG(Module):
    def __init__(self, platform, sys_clk_freq, iodelay_clk_freq):
        self.clock_domains.cd_sys                     = ClockDomain()
        # BUFMR to BUFR and BUFIO, "raw" clocks
        self.clock_domains.cd_sys4x_itermediate    = ClockDomain(reset_less=True)
        self.clock_domains.cd_sys4x_90_itermediate = ClockDomain(reset_less=True)

        self.clock_domains.cd_idelay                  = ClockDomain()

        # # #
        mmcm_ddr_rst = Signal()
        pll_rst = Signal()

        self.submodules.pll = pll = S7PLL(speedgrade=-3)
        self.comb += pll_rst.eq(~pll.locked)
        input_clk = platform.request("clk100")
        pll.register_clkin(input_clk, 100e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq, external_rst=mmcm_ddr_rst)

        self.submodules.pll_iodly = pll_iodly = S7PLL(speedgrade=-3)
        pll_iodly.register_clkin(input_clk, 100e6)
        pll_iodly.create_clkout(self.cd_idelay, iodelay_clk_freq)

        self.submodules.mmcm_ddr = mmcm_ddr = S7MMCM(speedgrade=-3)
        self.comb += mmcm_ddr_rst.eq(~mmcm_ddr.locked)
        mmcm_ddr.register_clkin(self.cd_sys.clk, sys_clk_freq)
        mmcm_ddr.create_clkout(
            self.cd_sys4x_itermediate,
            4 * sys_clk_freq,
            buf='bufmr',
            with_reset=False,
            name="sys4x_io",
            platform=platform
        )
        mmcm_ddr.create_clkout(
            self.cd_sys4x_90_itermediate,
            4 * sys_clk_freq,
            phase=90,
            with_reset=False,
            buf='bufmr',
            name="sys4x_90_io",
            platform=platform
        )

        self.submodules.idelayctrl = S7IDELAYCTRL(self.cd_idelay)

        # DDR5 PHY clock domains
        clock_domains = ["sys_io", "sys2x_io", "sys2x_90_io", "sys4x_io", "sys4x_90_io"]
        for bank_io in ["bank32", "bank33", "bank34"]:
            for clk_domain in clock_domains:
                buf_type = "BUFR"
                reset    = ~mmcm_ddr.locked | pll_rst
                if "4x" in clk_domain:
                    buf_type="BUFIO"
                    reset = None

                in_clk = ClockSignal("sys4x_itermediate")
                if "90" in clk_domain:
                    in_clk = ClockSignal("sys4x_90_itermediate")

                div = None
                if "sys4x_" not in clk_domain:
                    div = 4
                    if "2x" in clk_domain:
                        div = 2

                reset_less = True if reset is None else False
                setattr(self.clock_domains,
                        f"cd_{clk_domain}_{bank_io}",
                        ClockDomain(reset_less=reset_less, name=f"{clk_domain}_{bank_io}")
                )

                clk = ClockSignal(f"{clk_domain}_{bank_io}")
                buffer_dict = dict(
                    i_I=in_clk,
                    o_O=clk,
                )
                if div is not None:
                    buffer_dict["p_BUFR_DIVIDE"] = str(div)

                special = Instance(
                    buf_type,
                    **buffer_dict
                )

                self.specials += special
                if reset is not None:
                    cd = getattr(self, f"cd_{clk_domain}_{bank_io}")
                    self.specials += AsyncResetSynchronizer(cd, reset)


# SoC ----------------------------------------------------------------------------------------------

class SoC(common.RowHammerSoC):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # SPD EEPROM I2C ---------------------------------------------------------------------------
        self.submodules.i2c = I2CMaster(self.platform.request("i2c"))
        self.add_csr("i2c")

    def get_platform(self):
        return antmicro_ddr5_tester.Platform()

    def get_crg(self):
        return CRG(self.platform, self.sys_clk_freq,
            iodelay_clk_freq=float(self.args.iodelay_clk_freq))

    def get_ddr_pin_domains(self):
        return dict(
            ck_t=(("sys2x_io", "sys4x_io"), None),
            ck_c=(("sys2x_io", "sys4x_io"), None),
            A_ca=(("sys2x_io", "sys4x_io"), None),
            A_par=(("sys2x_io", "sys4x_io"), None),
            A_cs_n=(("sys2x_io", "sys4x_io"), None),
            B_ca=(("sys2x_io", "sys4x_io"), None),
            B_par=(("sys2x_io", "sys4x_io"), None),
            B_cs_n=(("sys2x_io", "sys4x_io"), None),
            reset_n=(("sys2x_io", "sys4x_io"), None),
            alert_n=(None, ("sys_io", "sys4x_io")),
            A_dq=(("sys2x_90_io", "sys4x_90_io"), ("sys_io", "sys4x_io")),
            A_dqs_t=(("sys2x_io", "sys4x_io"), ("sys_io", "sys4x_io")),
            A_dqs_c=(("sys2x_io", "sys4x_io"), ("sys_io", "sys4x_io")),
            B_dq=(("sys2x_90_io", "sys4x_90_io"), ("sys_io", "sys4x_io")),
            B_dqs_t=(("sys2x_io", "sys4x_io"), ("sys_io", "sys4x_io")),
            B_dqs_c=(("sys2x_io", "sys4x_io"), ("sys_io", "sys4x_io")),
        )

    def get_ddrphy(self):
        return ddr5.K7DDR5PHY(self.platform.request("ddr5"),
            iodelay_clk_freq  = float(self.args.iodelay_clk_freq),
            sys_clk_freq      = self.sys_clk_freq,
            with_sub_channels = True,
            direct_control    = False,
            pin_domains       = self.get_ddr_pin_domains(),
            pin_banks         = self.platform.pin_bank_mapping()["ddr5"],
        )

    def get_sdram_ratio(self):
        return "1:4"

    def add_host_bridge(self):
        self.submodules.ethphy = LiteEthS7PHYRGMII(
            clock_pads         = self.platform.request("eth_clocks"),
            pads               = self.platform.request("eth"),
            hw_reset_cycles    = math.ceil(float(self.args.eth_reset_time) * self.sys_clk_freq),
            rx_delay           = 0.8e-9,
            iodelay_clk_freq   = float(self.args.iodelay_clk_freq),
        )
        self.add_etherbone(
            phy          = self.ethphy,
            ip_address   = self.ip_address,
            mac_address  = self.mac_address,
            udp_port     = self.udp_port,
            buffer_depth = 256)

# Build --------------------------------------------------------------------------------------------

def main():
    parser = common.ArgumentParser(
        description  = "LiteX SoC on DDR5 Tester Board",
        sys_clk_freq = '200e6',
        module       = 'M329R8GA0BB0'
    )
    g = parser.add_argument_group(title="DDR5 Tester Board")
    parser.add(g, "--eth-reset-time", default="10e-3", help="Duration of Ethernet PHY reset")
    parser.add(g, "--iodelay-clk-freq", default="200e6", help="IODELAY clock frequency")
    vivado_build_args(g)
    args = parser.parse_args()

    soc_kwargs = common.get_soc_kwargs(args)
    soc = SoC(**soc_kwargs)
    soc.get_ddr_pin_domains()
    soc.platform.add_platform_command("set_property CLOCK_BUFFER_TYPE BUFG [get_nets sys_rst]")
    soc.platform.toolchain.pre_synthesis_commands.append("set_property strategy Congestion_SpreadLogic_high [get_runs impl_1]")
    soc.platform.toolchain.pre_synthesis_commands.append("set_property -name {{STEPS.OPT_DESIGN.ARGS.MORE OPTIONS}} -value {{-merge_equivalent_drivers -hier_fanout_limit 1000}} -objects [get_runs impl_1]")

    target_name = 'ddr5_tester'
    builder_kwargs = common.get_builder_kwargs(args, target_name=target_name)
    builder = Builder(soc, **builder_kwargs)
    build_kwargs = vivado_build_argdict(args) if not args.sim else {}
    if not args.sim:
        build_kwargs["vivado_place_directive"] = "AltSpreadLogic_high"
        build_kwargs["vivado_post_place_phys_opt_directive"] = "AggressiveExplore"
        build_kwargs["vivado_route_directive"] = "AlternateCLBRouting"

    common.run(args, builder, build_kwargs, target_name=target_name)

if __name__ == "__main__":
    main()
