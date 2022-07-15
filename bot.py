import subprocess
import socket
import requests
import json
import os


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
    cmd = ["/usr/sge/bin/linux-x64/qstat",  "-u",  "mrok", "|", "grep", "-v", "LowPri"]
    cmd = " ".join(cmd)
    mirai = get_output(cmd, shell=True)
    mirai = "`mirai updates:`\n```\n" + mirai + "```\n"

    with open("mirai.txt") as f:
        mirai_last = f.read()

    with open("mirai.txt", "w") as f:
        f.write(mirai)

    if mirai != mirai_last:
        post_slack(mirai)

if __name__ == "__main__":
    check_loop()