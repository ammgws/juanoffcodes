# Powershell script to send WOL magic packet.
# Can run directly or via accompanying batch file

param (
    [Parameter(Mandatory=$true)][string]$MacAddress
)

# split MAC address string and convert to bytes
$MacByteArray = $MacAddress -split "[:-]" | ForEach-Object { [Byte] "0x$_"}

# build magic packet (FF repeated 6 times followed by MCA repeated 16 times)
[Byte[]] $MagicPacket = (,0xFF * 6) + ($MacByteArray * 16)

# open UDP socket and send magic packet to the network broadcast address
$UdpClient = New-Object System.Net.Sockets.UdpClient
$UdpClient.Connect(([System.Net.IPAddress]::Broadcast), 9) # use port 9
$UdpClient.Send($MagicPacket,$MagicPacket.Length)
$UdpClient.Close()