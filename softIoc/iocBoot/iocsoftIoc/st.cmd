#!../../bin/darwin-x86/softIoc

#- You may have to change softIoc to something else
#- everywhere it appears in this file

#< envPaths

## Register all support components
dbLoadDatabase("../../dbd/softIoc.dbd",0,0)
softIoc_registerRecordDeviceDriver(pdbbase)

## Load record instances
dbLoadRecords("../../db/softIoc.db","user=klauer")

iocInit()

## Start any sequence programs
#seq sncsoftIoc,"user=klauer"
