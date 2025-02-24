import json
import os
import signal
import socket
from io import StringIO
from time import sleep

import pandas as pd
import paramiko
import requests
from paramiko_expect import SSHClientInteraction
from slack_sdk.web import WebClient


class TimeoutException(Exception):
    def __init__(self, seconds, msg=""):
        self.timeout_limit = seconds
        if msg != "":
            msg = ": " + msg
        super().__init__(f"Timeout {seconds} sec" + msg)


class TimeoutContext:
    def __init__(self, seconds, err_msg=""):
        self.seconds = seconds
        self.err_msg = err_msg

    def handler(self, signum, frame):
        raise TimeoutException(self.seconds, self.err_msg)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handler)
        signal.alarm(self.seconds)

    def __exit__(self, exc_type, exc_value, traceback):
        signal.alarm(0)
        signal.signal(signal.SIGALRM, signal.SIG_DFL)


PROMPT = "(\([\-0-9A-z_]+\)\s)?~\s>\s"  # noqa: W605


user = os.environ["SSH_USER"]

host = os.environ["SSH_GATEWAY_HOST"]
machine = os.environ["SSH_MACHINE"]

DATECMD = os.environ["DATECMD"]
DATEK = os.environ["DATEK"]
DATEN = os.environ["DATEN"]
DATEP = os.environ["DATEP"]
DATEQSTAT = os.environ["DATEQSTAT"]


def check_date():
    try:
        with TimeoutContext(60):
            with get_interaction() as interact:
                interact.send("")
                interact.expect(PROMPT)

                interact.send('eval "$(ssh-agent)"')
                interact.expect(PROMPT)

                interact.send("ssh-add " + DATEK)
                sleep(3)

                interact.send(DATEP)
                interact.expect(PROMPT)

                interact.send(DATECMD)
                interact.expect(PROMPT)

                interact.send(DATEQSTAT)
                interact.expect(PROMPT)

                output = interact.current_output
                output = "\n".join(output.split("\n")[1:-1])

                output = output.replace(" R ", " :pi-run: ")
                output = output.replace(" Q ", " :gre-humming: ")
                output = output.replace("  ", " ")
                output = output.replace(f"~ > {DATECMD}", "")

                if ":" not in output:
                    output = ":ジョブなし:"

                post_lab_slack(output, DATEN, ":datem:")

                return None

    except TimeoutException:
        post_lab_slack(":maintenance:", DATEN, ":datem:")


def post_lab_slack(text: str, username="mirai", emoji: str = ":ssh-mirai:") -> None:
    web_client = WebClient(token=os.environ["LAB_TOKEN"])
    web_client.chat_postMessage(
        text=text,
        channel=os.environ["LAB_CHANNEL"],
        username=username,
        icon_emoji=emoji,
    )


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


def get_interaction():
    proxy = paramiko.ProxyCommand(f"ssh {user}@{host} -p 22 nc {machine} 22")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
    client.connect(machine, port=22, username=user, sock=proxy)

    def output(x):
        return None

    return SSHClientInteraction(
        client, timeout=10, display=True, output_callback=output, tty_width=250
    )


def get_output(command: str) -> None:
    with get_interaction() as interact:
        interact.send("")
        interact.expect(PROMPT)

        interact.send(command)
        interact.expect(PROMPT)

        output = interact.current_output
        output = "\n".join(output.split("\n")[1:-1])
        return output


def lab_update():
    usage = get_output("/usr/sge/bin/linux-x64/qstat -f")
    # usage = f"```\n{usage}\n```"
    post_lab_slack(usage)

    mirai = get_output("/usr/sge/bin/linux-x64/qstat")
    mirai = f"```\n{mirai}\n```"
    mirai_last = ""
    if os.path.exists("mirai.txt"):
        with open("mirai.txt") as f:
            mirai_last = f.read()

    with open("mirai.txt", "w") as f:
        f.write(mirai)

    if mirai != mirai_last:
        # post_slack(mirai)
        post_lab_slack(mirai)


def pretty_lab_update():
    qstat = get_output("/usr/sge/bin/linux-x64/qstat  -f | grep BIP")
    df = pd.read_csv(
        StringIO(qstat),
        sep="\s+",  # noqa: W605
        names=["queue", "bip", "reserve", "load", "os"],
    )

    df["group"] = df.queue.str.split("@").str[0]
    df["reserved_cpus"] = df.reserve.str.split("/").str[1]
    df["equipped_cpus"] = df.reserve.str.split("/").str[2]

    msg = ""

    for group in df.group.unique():
        msg += f"*{group}*\n"

        subd = df[df.group == group]
        states = []
        load_states = []
        for _, row in subd.iterrows():

            if row.reserved_cpus == row.equipped_cpus:
                states.append(":全力:")
            elif row.reserved_cpus == "0":
                states.append(":ジョブなし:")
            else:
                states.append(":余裕:")

            if row.load > float(row.equipped_cpus) + 0.5:
                load_states.append(":cpu利用率超過:")
            elif row.load > float(row.equipped_cpus) - 0.5:
                load_states.append(":全力:")
            elif row.load < 0.5:
                load_states.append(":ジョブなし:")
            else:
                load_states.append(":余裕:")
        msg += " ".join(states) + " reserved\n"
        msg += " ".join(load_states) + " actual\n"

    post_lab_slack(msg)


def my_update():
    cmd = ["/usr/sge/bin/linux-x64/qstat", "-u", user, "|", "grep", "-v", "compute-3-1"]
    cmd = " ".join(cmd)

    my_mirai = get_output(cmd)

    my_mirai = "`mirai updates:`\n```\n" + my_mirai + "```\n"

    mirai_last = ""
    if os.path.exists("my_mirai.txt"):
        with open("my_mirai.txt") as f:
            mirai_last = f.read()

    with open("my_mirai.txt", "w") as f:
        f.write(my_mirai)

    if my_mirai != mirai_last:
        post_slack(my_mirai)


def memory_usage():
    qhost = get_output("/usr/sge/bin/linux-x64/qhost")
    # post_lab_slack(f"```\n{qhost}\n```\n")
    df = pd.read_csv(
        StringIO(qhost),
        skiprows=3,
        sep="\s+",  # noqa: W605
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

    # df.used_mem / df.max_mem > 0.9

    df["MEMUSE"] = df.used_mem / df.max_mem * 100

    high_memory = df[df["MEMUSE"] > 95]

    qstat = get_output("/usr/sge/bin/linux-x64/qstat | tail -n +3")

    df_qstat = pd.read_csv(
        StringIO(qstat),
        sep="\s+",  # noqa: W605
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

    if len(merged_df) > 0:
        msg = ""
        for _, row in merged_df.iterrows():
            msg += f"@{row.user}\n:warning: {row.queue}のジョブ#{row.jobID}が"
            msg += f"{row.MEMUSE:.3g}%ものメモリを消費してしまっています。"
            msg += "低速化やクラッシュの恐れがあります。\n"
            msg += "よりメモリの大きなノードを使用しましょう。\n"

        # post_slack(msg)
        post_lab_slack(msg)

    df["free_cpus"] = df.load - df.cores
    df_overcpu = df[df.free_cpus > 1]

    df_overcpu = df_overcpu.merge(df_qstat, how="inner")

    if len(df_overcpu) > 0:
        msg = ""
        for _, row in df_overcpu.iterrows():
            msg += f"@{row.user}\n:warning: {row.queue}のジョブ#{row.jobID}が"
            msg += "割り当てコア数以上のCPUを消費しています。"
            msg += "並列化の問題か、ゾンビプロセスの存在の可能性があります。\n"

        # post_slack(msg)
        post_lab_slack(msg)


def main():

    try:
        memory_usage()
        lab_update()
        pretty_lab_update()
        check_date()
    except paramiko.ssh_exception.SSHException:
        sleep(180)
        main()


if __name__ == "__main__":
    main()
