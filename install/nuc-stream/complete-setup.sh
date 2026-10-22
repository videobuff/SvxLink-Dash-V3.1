#!/bin/bash
set -euo pipefail
export SSH_AUTH_SOCK=/home/erik/.ssh/pi3twe-agent.sock
ssh -t -o ConnectTimeout=10 erik@5.2.72.156 'sudo bash /home/erik/finish-pi3twe-nuc-stream.sh'
sudo bash /home/erik/pi3twe-nuc-stream/finish-cleanup.sh
echo 'Inrichting toegepast. Luisteradres: https://stream.pa0esh.nl/nuc/'
