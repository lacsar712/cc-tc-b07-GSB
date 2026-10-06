<script>
  const MEASURE_TYPES = ["拱顶", "边墙", "注浆段"];

  let session = null;
  let logs = [];
  let flows = [];
  let page = "logs";
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let deltaMm = "";
  let measureType = "拱顶";
  let selected = new Set();
  let preview = null;
  let notice = "";
  let error = "";
  let loading = false;
  let timer;

  $: isWriter = session?.role === "writer";
  $: doneLogs = logs.filter((r) => r.status === "done");
  // 勾选顺序按编号展示；跨类/未办结在拦截时给出提示，最终以后台拒收为准。
  $: selectedRows = logs.filter((r) => selected.has(r.id));
  $: selectedTypes = new Set(selectedRows.map((r) => r.measure_type));
  $: mixedType = selectedTypes.size > 1;
  $: previewValid =
    preview &&
    preview.ids.length === selectedRows.length &&
    preview.ids
      .slice()
      .sort((a, b) => a - b)
      .join(",") ===
      selectedRows
        .map((r) => r.id)
        .slice()
        .sort((a, b) => a - b)
        .join(",");

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refreshLogs() {
    if (!session) return;
    const res = await fetch("/api/logs", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) logs = await res.json();
  }

  async function refreshFlows() {
    if (!session) return;
    const res = await fetch("/api/merge/flows", { headers: headers() });
    if (res.ok) flows = await res.json();
  }

  async function refresh() {
    await refreshLogs();
    if (page === "merge") await refreshFlows();
  }

  async function login() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: loginUser, password: loginPass }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "登录失败";
        return;
      }
      session = { token: data.access_token, username: data.username, role: data.role };
      localStorage.setItem("tunnel_session", JSON.stringify(session));
      await refreshLogs();
      timer = setInterval(refresh, 2000);
    } catch {
      error = "无法连接接口";
    } finally {
      loading = false;
    }
  }

  function logout() {
    if (timer) clearInterval(timer);
    session = null;
    logs = [];
    flows = [];
    selected = new Set();
    preview = null;
    page = "logs";
    localStorage.removeItem("tunnel_session");
  }

  async function switchPage(next) {
    page = next;
    error = "";
    notice = "";
    if (next === "merge") {
      await refreshFlows();
    } else {
      selected = new Set();
      preview = null;
    }
  }

  async function submit() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({
          chainage,
          delta_mm: Number(deltaMm),
          measure_type: measureType,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      await refreshLogs();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  function toggle(row) {
    if (row.status !== "done") {
      error = `编号 ${row.id} 尚未办结，不能勾进合成`;
      return;
    }
    const next = new Set(selected);
    if (next.has(row.id)) {
      next.delete(row.id);
    } else {
      if (selectedTypes.size > 0 && !selectedTypes.has(row.measure_type)) {
        error = `不能混勾：已选类别为 ${[...selectedTypes].join("、")}，不能再勾 ${row.measure_type}`;
        return;
      }
      next.add(row.id);
    }
    selected = next;
    preview = null;
    error = "";
    notice = "";
  }

  async function previewMerge() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/merge/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ ids: [...selected] }),
      });
      const data = await res.json();
      if (!res.ok) {
        preview = null;
        error = data.detail || "预览失败";
        return;
      }
      preview = data;
    } catch {
      error = "预览时网络异常";
    } finally {
      loading = false;
    }
  }

  async function generateMerge() {
    error = "";
    notice = "";
    loading = true;
    try {
      const res = await fetch("/api/merge", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ ids: preview.ids }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "生成失败";
        return;
      }
      notice = `已生成新单 #${data.log.id}：${data.log.measure_type} ${data.log.delta_mm} mm，状态待认领；合成流水 #${data.flow.id} 已同笔记账。`;
      selected = new Set();
      preview = null;
      await Promise.all([refreshLogs(), refreshFlows()]);
    } catch {
      error = "生成时网络异常";
    } finally {
      loading = false;
    }
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refreshLogs();
      timer = setInterval(refresh, 2000);
    } catch {
      localStorage.removeItem("tunnel_session");
    }
  }
</script>

<style>
  :global(body) {
    margin: 0;
    font-family: "Segoe UI", system-ui, sans-serif;
    background: #1c1917;
    color: #f5f5f4;
  }
  main { max-width: 1000px; margin: 0 auto; padding: 1.5rem; }
  header { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.25rem; }
  h1 { color: #fbbf24; margin: 0; }
  nav { display: flex; gap: 0.5rem; margin-left: auto; }
  nav button { background: #44403c; }
  nav button.active { background: #d97706; }
  .sub { color: #a8a29e; margin: 0.25rem 0 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input, select {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button.secondary { background: #57534e; }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  .err { color: #fb7185; }
  .ok-note { color: #86efac; }
  .warn-note { color: #fde68a; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .type-拱顶 { background: #1e3a8a; color: #bfdbfe; }
  .type-边墙 { background: #4c1d95; color: #ddd6fe; }
  .type-注浆段 { background: #134e4a; color: #99f6e4; }
  .preview-box {
    background: #0c0a09; border: 1px dashed #a16207; border-radius: 6px;
    padding: 0.75rem 1rem; margin: 0.75rem 0;
  }
  .preview-box .avg { font-size: 1.5rem; color: #fbbf24; font-weight: 700; }
</style>

<main>
  {#if !session}
    <h1>隧道收敛测缝台</h1>
    <p class="sub">测量员提交桩号与收敛毫米值，接口进程内线程认领后出结论。登录框已预填可写账号 surveyor / surv123456。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else}
    <header>
      <h1>隧道收敛测缝台</h1>
      <nav>
        <button class={page === "logs" ? "active" : ""} on:click={() => switchPage("logs")}>测缝台账</button>
        <button class={page === "merge" ? "active" : ""} on:click={() => switchPage("merge")}>合成专页</button>
      </nav>
    </header>
    <p class="sub">
      已登录：{session.username}（{isWriter ? "可提交/可生成" : "只读：可看预览，不能代点生成"}）
    </p>
    <section>
      <button class="secondary" on:click={logout}>退出</button>
      <button class="secondary" disabled={loading} on:click={refresh}>刷新列表</button>
    </section>

    {#if page === "logs"}
      {#if isWriter}
        <section>
          <label>测缝类别</label>
          <select bind:value={measureType}>
            {#each MEASURE_TYPES as t}<option value={t}>{t}</option>{/each}
          </select>
          <label>里程桩号</label>
          <input placeholder="例如 K20+050" bind:value={chainage} />
          <label>收敛（毫米，可正可负）</label>
          <input type="number" step="0.1" bind:value={deltaMm} />
          <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
          {#if error}<p class="err">{error}</p>{/if}
        </section>
      {/if}
      <section>
        <table>
          <thead>
            <tr><th>编号</th><th>类别</th><th>桩号</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th></tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>{row.id}</td>
                <td><span class="tag type-{row.measure_type}">{row.measure_type}</span></td>
                <td>{row.chainage}</td>
                <td>{row.delta_mm}</td>
                <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待认领' : '已办结'}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
                <td>{row.reason ?? "—"}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>
    {:else}
      <section>
        <h2 style="margin-top:0">已办结测缝合成</h2>
        <p class="sub" style="margin-bottom:0.5rem">
          勾选至少两笔<b>同类已办结</b>测缝，先看后台算出的平均预览，再生成新的待认领单。
          拱顶、边墙、注浆段不得混勾；未办结不可勾选。
        </p>
        {#if mixedType}<p class="err">当前勾选跨了类别，后台会拒收。</p>{/if}
        <table>
          <thead>
            <tr><th>勾选</th><th>编号</th><th>类别</th><th>桩号</th><th>收敛mm</th><th>状态</th><th>结论</th></tr>
          </thead>
          <tbody>
            {#each logs as row}
              <tr>
                <td>
                  <input
                    style="width:auto;margin:0"
                    type="checkbox"
                    checked={selected.has(row.id)}
                    disabled={row.status !== "done"}
                    on:click={() => toggle(row)}
                  />
                </td>
                <td>{row.id}</td>
                <td><span class="tag type-{row.measure_type}">{row.measure_type}</span></td>
                <td>{row.chainage}</td>
                <td>{row.delta_mm}</td>
                <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待认领（不可勾）' : '已办结'}</span></td>
                <td>
                  {#if row.verdict}
                    <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                  {:else}—{/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>

        <div style="margin-top:0.75rem;display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap">
          <button
            disabled={loading || selectedRows.length < 2 || mixedType}
            on:click={previewMerge}
          >
            预览后台平均（已选 {selectedRows.length} 笔）
          </button>
          {#if isWriter}
            <button disabled={loading || !previewValid} on:click={generateMerge}>
              生成合成新单
            </button>
          {:else}
            <span class="warn-note">巡检员只读：可看预览，不能代点生成。</span>
          {/if}
        </div>

        {#if error}<p class="err">{error}</p>{/if}
        {#if notice}<p class="ok-note">{notice}</p>{/if}

        {#if preview}
          <div class="preview-box">
            <div>合成类别：<span class="tag type-{preview.measure_type}">{preview.measure_type}</span>　来源 {preview.count} 笔：#{preview.ids.join("、#")}</div>
            <div style="margin-top:0.4rem">后台算出的平均收敛：<span class="avg">{preview.average_mm}</span> mm（以记账值为准）</div>
            <ul style="margin:0.5rem 0 0;padding-left:1.25rem">
              {#each preview.sources as s}
                <li>#{s.id} {s.chainage} {s.delta_mm} mm（{s.verdict}）</li>
              {/each}
            </ul>
            {#if !previewValid}<p class="warn-note" style="margin-bottom:0">勾选已变更，请重新预览再生成。</p>{/if}
          </div>
        {/if}
      </section>

      <section>
        <h2 style="margin-top:0">合成流水</h2>
        {#if flows.length === 0}
          <p class="sub">还没有合成记录。</p>
        {:else}
          <table>
            <thead>
              <tr><th>流水号</th><th>类别</th><th>来源编号</th><th>平均mm</th><th>新单号/状态</th><th>生成人</th></tr>
            </thead>
            <tbody>
              {#each flows as f}
                <tr>
                  <td>{f.id}</td>
                  <td><span class="tag type-{f.measure_type}">{f.measure_type}</span></td>
                  <td>#{f.source_ids.join("、#")}</td>
                  <td>{f.average_mm}</td>
                  <td>
                    #{f.result_log_id}
                    {#if f.result}
                      <span class="tag {f.result.status === 'pending' ? 'pending' : 'ok'}">{f.result.status === 'pending' ? '待认领' : '已办结'}</span>
                    {/if}
                  </td>
                  <td>{f.created_by}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>
    {/if}
  {/if}
</main>
