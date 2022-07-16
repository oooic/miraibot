import subprocess
import paramiko
import socket
import requests
import json
import os

PROMPT = "(\([\-0-9A-z_]+\)\s)?~\s>\s"  # noqa: W605



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


def get_ito_nakayamalab_from_client(interact, rg):

    interact.send(cmd)
    interact.expect(PROMPT)
    return get_nakayamalab_info(interact.current_output)



def check_loop():
    ssh_config = paramiko.SSHConfig()
    ssh_config.from_text(os.environ['SSH_CONFIG'])
    config = ssh_config.lookup("mirai")

    with paramiko.SSHClient() as client:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())


        client.connect(
             config['hostname'],
            username=config['user'],
            key_filename=config['identityfile'],
            timeout=15.0
        )


        with SSHClientInteraction(client, timeout=10, display=True, output_callback=output, tty_width=250) as interact:
            interact.send("")
            interact.expect(PROMPT)
            txt = ""

            cmd = ["/usr/sge/bin/linux-x64/qstat",  "-u", config['user'], "|", "grep", "-v", "LowPri"]
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