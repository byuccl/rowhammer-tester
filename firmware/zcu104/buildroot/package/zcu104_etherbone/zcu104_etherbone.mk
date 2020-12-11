ZCU104_ETHERBONE_VERSION = 1.0
ZCU104_ETHERBONE_SITE = $(BR2_EXTERNAL_ZCU104_ROW_HAMMER_PATH)/../etherbone
ZCU104_ETHERBONE_SITE_METHOD = local
ZCU104_ETHERBONE_INSTALL_TARGET = YES

define ZCU104_ETHERBONE_BUILD_CMDS
$(MAKE) CC="$(TARGET_CC)" LD="$(TARGET_LD)" -C $(@D) all
endef

define ZCU104_ETHERBONE_INSTALL_TARGET_CMDS
$(INSTALL) -D -m 0755 $(@D)/build/zcu104_etherbone $(TARGET_DIR)/bin
endef

define ZCU104_ETHERBONE_INSTALL_INIT_SYSV
$(INSTALL) -D -m 0755 $(ZCU104_ETHERBONE_PKGDIR)/zcu104_etherbone-init $(TARGET_DIR)/etc/init.d/S90zcu104_etherbone
endef

$(eval $(generic-package))
