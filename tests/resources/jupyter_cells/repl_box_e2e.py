# %%
import repl_box


# %%
def mul(x, y):
    return x * y


# %% EXPECT: 42
with repl_box.start(socket_path="/tmp/repl-box-e2e.sock", mul=mul) as repl:
    result = repl.send("mul(6, 7)")
    print(result["stdout"].strip())
