TOP=../..

include $(TOP)/configure/CONFIG
#----------------------------------------
#  ADD MACRO DEFINITIONS AFTER THIS LINE
#=============================

#=============================
# Build the IOC application

PROD_IOC = softIoc
# softIoc.dbd will be created and installed
DBD += softIoc.dbd

# softIoc.dbd will be made up from these files:
softIoc_DBD += base.dbd

# Include dbd files from all support applications:
softIoc_DBD += asynRecord.dbd
softIoc_DBD += iocAdmin.dbd
softIoc_DBD += devIocStats.dbd

# Add all the support libraries needed by this IOC
softIoc_LIBS += asyn
softIoc_LIBS += seq
softIoc_LIBS += devIocStats

# softIoc_registerRecordDeviceDriver.cpp derives from softIoc.dbd
softIoc_SRCS += softIoc_registerRecordDeviceDriver.cpp

# Build the main IOC entry point on workstation OSs.
softIoc_SRCS_DEFAULT += softIocMain.cpp
softIoc_SRCS_vxWorks += -nil-

# Add support from base/src/vxWorks if needed
#softIoc_OBJS_vxWorks += $(EPICS_BASE_BIN)/vxComLibrary

# Finally link to the EPICS Base libraries
softIoc_LIBS += $(EPICS_BASE_IOC_LIBS)

#===========================

include $(TOP)/configure/RULES
#----------------------------------------
#  ADD RULES AFTER THIS LINE
