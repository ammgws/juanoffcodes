REM Sends WOL magic packet to the specified MAC address using accompanying powershell script
REM enter your mac address below, in the form xx:xx:xx:xx:xx:xx
set mac="xx:xx:xx:xx:xx:xx"
start powershell.exe -ExecutionPolicy RemoteSigned -Command "& {.\\send_wol.ps1 -MacAddress %mac%}"
exit 0