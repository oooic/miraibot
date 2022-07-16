import subprocess
import paramiko
import socket
import requests
import json
import os
from paramiko_expect import SSHClientInteraction

PROMPT = "(\([\-0-9A-z_]+\)\s)?~\s>\s"  # noqa: W605


user = os.environ['SSH_USER']

host = os.environ['SSH_GATEWAY_HOST']
machine = os.environ['SSH_MACHINE']


def post_slack(text):
    WEB_HOOK_URL = os.environ['WEB_HOOK_URL']
    requests.post(
        WEB_HOOK_URL,
        data=json.dumps(
            {
                "text": text,
                "username": "stat bot ({0})".format(socket.gethostname()),
                "link_names": 1,  # 名前をリンク化
            }
        ),
    )


def get_output(cmd, shell=False):
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=shell
    )

    out,  err = p.communicate()
    out = out.decode("utf-8")
    err = err.decode("utf-8")

    return out


def check_loop():

    proxy = paramiko.ProxyCommand(f"ssh {user}@{host} -p 22 nc {machine} 22")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
    client.connect(
        machine,
        port=22,
        username=user,
        sock=proxy
    )


    with SSHClientInteraction(client, timeout=10, display=True, tty_width=250) as interact:
        interact.send("")
        interact.expect(PROMPT)
        txt = ""

        cmd = ["/usr/sge/bin/linux-x64/qstat",  "-u", user, "|", "grep", "-v", "LowPri"]
        cmd = " ".join(cmd)

        interact.send(cmd)
        interact.expect(PROMPT)

        mirai = interact.current_output

        mirai = "`mirai updates:`\n```\n" + mirai + "```\n"

        mirai_last = ""
        if os.path.exists("mirai.txt"):
            with open("mirai.txt") as f:
                mirai_last = f.read()

        with open("mirai.txt", "w") as f:
            f.write(mirai)

        if mirai != mirai_last:
            post_slack(mirai)

if __name__ == "__main__":
    check_loop()