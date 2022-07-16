import json
import os
import socket
from io import StringIO

import pandas as pd
import paramiko
import requests
from paramiko_expect import SSHClientInteraction

PROMPT = "(\([\-0-9A-z_]+\)\s)?~\s>\s"  # noqa: W605


user = os.environ["SSH_USER"]

host = os.environ["SSH_GATEWAY_HOST"]
machine = os.environ["SSH_MACHINE"]


def post_slack(text: str) -> None:
    WEB_HOOK_URL = os.environ["WEB_HOOK_URL"]
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


def get_output(command: str) -> None:
    proxy = paramiko.ProxyCommand(f"ssh {user}@{host} -p 22 nc {machine} 22")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
    client.connect(machine, port=22, username=user, sock=proxy)

    def output(x):
        return None

    with SSHClientInteraction(
        client, timeout=10, display=True, output_callback=output, tty_width=250
    ) as interact:
        interact.send("")
        interact.expect(PROMPT)
        txt = ""

        interact.send(command)
        interact.expect(PROMPT)

        mirai = interact.current_output
        return mirai


def my_update():
    cmd = ["/usr/sge/bin/linux-x64/qstat", "-u", user, "|", "grep", "-v", "LowPri"]
    cmd = " ".join(cmd)

    my_mirai = get_output(cmd)

    my_mirai = "`mirai updates:`\n```\n" + my_mirai + "```\n"

    mirai_last = ""
    if os.path.exists("mirai.txt"):
        with open("mirai.txt") as f:
            mirai_last = f.read()

    with open("mirai.txt", "w") as f:
        f.write(mirai)

    if mirai != mirai_last:
        post_slack(mirai)


def memory_usage():
    qhost = get_output("/usr/sge/bin/linux-x64/qhost")
    df = pd.read_csv(
        StringIO(qhost),
        skiprows=3,
        sep="\s+",
        names=[
            "node",
            "os",
            "cores",
            "load",
            "max_mem",
            "used_mem",
            "max_swap",
            "used_swap",
        ],
    )

    for mem in "max_mem", "used_mem", "max_swap", "used_swap":
        df.loc[:, mem] = (
            df[mem].str.replace("M", "e3").str.replace("G", "e6").astype(float)
        )

    df.used_mem / df.max_mem > 0.9

    high_memory = df[df.used_mem / df.max_mem > 0.7]

    qstat = get_output("/usr/sge/bin/linux-x64/qstat | tail -n +3")

    df_qstat = pd.read_csv(
        StringIO(qstat),
        sep="\s+",
        names=[
            "jobID",
            "prior",
            "name",
            "user",
            "state",
            "date",
            "time",
            "queue",
            "slots",
        ],
    )

    df_qstat["node"] = df_qstat.queue.str.split("@").str[1]

    merged_df = high_memory.merge(df_qstat, how="inner")

    msg = ""
    for _, row in merged_df.iterrows():
        f"@{row.name}\nJOB ID{row.jobID}"


def main():
    my_update()


if __name__ == "__main__":
    main()
