<script>
  let session = null;
  let logs = [];
  let merges = [];
  let view = "logs";
  let loginUser = "surveyor";
  let loginPass = "surv123456";
  let chainage = "";
  let segment = "拱顶";
  let deltaMm = "";
  let error = "";
  let mergeError = "";
  let mergeNotice = "";
  let loading = false;
  let preview = null;
  let lastMerge = null;
  let selectedIds = [];
  let timer;

  const SEGMENTS = ["拱顶", "边墙", "注浆段"];

  $: isWriter = session?.role === "writer";
  $: selectedCount = selectedIds.length;

  function headers() {
    return session ? { Authorization: "Bearer " + session.token } : {};
  }

  async function refresh() {
    if (!session) return;
    const res = await fetch("/api/logs", { headers: headers() });
    if (res.status === 401) {
      logout();
      return;
    }
    if (res.ok) {
      logs = await res.json();
      const alive = new Set(logs.map((r) => r.id));
      selectedIds = selectedIds.filter((id) => alive.has(id));
    }
  }

  async function refreshMerges() {
    if (!session) return;
    const res = await fetch("/api/merges", { headers: headers() });
    if (res.ok) merges = await res.json();
  }

  function showView(v) {
    view = v;
    mergeError = "";
    mergeNotice = "";
    preview = null;
    if (v === "merge") refreshMerges();
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
      await refresh();
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
    merges = [];
    selectedIds = [];
    preview = null;
    lastMerge = null;
    view = "logs";
    localStorage.removeItem("tunnel_session");
  }

  async function submit() {
    error = "";
    loading = true;
    try {
      const res = await fetch("/api/logs", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ chainage, segment, delta_mm: Number(deltaMm) }),
      });
      const data = await res.json();
      if (!res.ok) {
        error = data.detail || "提交失败";
        return;
      }
      chainage = "";
      deltaMm = "";
      await refresh();
    } catch {
      error = "提交时网络异常";
    } finally {
      loading = false;
    }
  }

  function toggle(id) {
    if (selectedIds.includes(id)) {
      selectedIds = selectedIds.filter((x) => x !== id);
    } else {
      selectedIds = [...selectedIds, id];
    }
    preview = null;
    mergeError = "";
    mergeNotice = "";
  }

  // 平均值一律由后台计算并记账，前端只展示后台返回的预览结果
  async function previewMerge() {
    mergeError = "";
    mergeNotice = "";
    preview = null;
    loading = true;
    try {
      const res = await fetch("/api/merges/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ log_ids: selectedIds }),
      });
      const data = await res.json();
      if (!res.ok) {
        mergeError = data.detail || "预览被拒收";
        return;
      }
      preview = data;
    } catch {
      mergeError = "预览时网络异常";
    } finally {
      loading = false;
    }
  }

  async function generateMerge() {
    mergeError = "";
    mergeNotice = "";
    loading = true;
    try {
      const res = await fetch("/api/merges", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ log_ids: selectedIds }),
      });
      const data = await res.json();
      if (!res.ok) {
        mergeError = data.detail || "合成被拒收";
        return;
      }
      lastMerge = data;
      mergeNotice =
        "已生成新待认领单 #" + data.log.id +
        "（部位 " + data.log.segment + "，后台平均 " + data.batch.average_mm + " mm），" +
        "合成流水 #" + data.batch.id + " 已一并记账";
      selectedIds = [];
      preview = null;
      await refresh();
      await refreshMerges();
    } catch {
      mergeError = "合成时网络异常";
    } finally {
      loading = false;
    }
  }

  const raw = localStorage.getItem("tunnel_session");
  if (raw) {
    try {
      session = JSON.parse(raw);
      refresh();
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
  main { max-width: 960px; margin: 0 auto; padding: 1.5rem; }
  h1 { color: #fbbf24; margin: 0; }
  h2 { color: #fcd34d; font-size: 1.05rem; margin: 0 0 0.5rem; }
  .topbar {
    display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;
    border-bottom: 1px solid #44403c; padding-bottom: 0.75rem; margin-bottom: 1rem;
  }
  .topbar nav { display: flex; gap: 0.5rem; flex: 1; }
  .topbar nav button {
    background: transparent; color: #d6d3d1; border: 1px solid #57534e;
  }
  .topbar nav button.active {
    background: #d97706; border-color: #d97706; color: #fff;
  }
  .who { display: flex; align-items: center; gap: 0.5rem; color: #a8a29e; font-size: 0.85rem; }
  .sub { color: #a8a29e; margin-bottom: 1.25rem; }
  section {
    background: #292524; border: 1px solid #44403c; border-radius: 8px;
    padding: 1rem 1.25rem; margin-bottom: 1rem;
  }
  label { display: block; font-size: 0.85rem; color: #d6d3d1; margin-bottom: 0.25rem; }
  input, select {
    width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px;
    border: 1px solid #57534e; background: #0c0a09; color: #fafaf9; margin-bottom: 0.75rem;
  }
  input[type="checkbox"] { width: auto; margin: 0; }
  button {
    cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px;
    background: #d97706; color: #fff; font-weight: 600;
  }
  button:disabled { opacity: 0.45; cursor: not-allowed; }
  button.secondary { background: #57534e; }
  .err { color: #fb7185; }
  .notice { color: #86efac; }
  .hint { color: #a8a29e; font-size: 0.85rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #44403c; }
  .tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
  .ok { background: #14532d; color: #86efac; }
  .bad { background: #7f1d1d; color: #fca5a5; }
  .pending { background: #713f12; color: #fde68a; }
  .preview {
    margin-top: 0.75rem; padding: 0.75rem 1rem; border-radius: 6px;
    border: 1px dashed #d97706; background: #0c0a09;
  }
  .preview p { margin: 0.25rem 0; }
  .actions { display: flex; gap: 0.5rem; align-items: center; margin-top: 0.5rem; flex-wrap: wrap; }
</style>

<main>
  <header class="topbar">
    <h1>隧道收敛测缝台</h1>
    {#if session}
      <nav>
        <button class:active={view === "logs"} on:click={() => showView("logs")}>测缝台账</button>
        <button class:active={view === "merge"} on:click={() => showView("merge")}>合成专页</button>
      </nav>
      <div class="who">
        <span>{session.username}（{isWriter ? "测量员" : "巡检员"}）</span>
        <button class="secondary" on:click={logout}>退出</button>
      </div>
    {/if}
  </header>
  {#if !session}
    <p class="sub">测量员提交桩号与收敛毫米值，接口进程内线程认领后出结论。登录框已预填可写账号 surveyor / surv123456。</p>
    <section>
      <label>用户名</label>
      <input bind:value={loginUser} autocomplete="off" />
      <label>密码</label>
      <input type="password" bind:value={loginPass} autocomplete="off" />
      <button disabled={loading} on:click={login}>登录</button>
      {#if error}<p class="err">{error}</p>{/if}
    </section>
  {:else if view === "logs"}
    <p class="sub">已登录：{session.username}（{isWriter ? "可提交" : "只读"}）</p>
    <section>
      <button class="secondary" disabled={loading} on:click={refresh}>刷新列表</button>
    </section>
    {#if isWriter}
      <section>
        <label>里程桩号</label>
        <input placeholder="例如 K20+050" bind:value={chainage} />
        <label>部位类别</label>
        <select bind:value={segment}>
          {#each SEGMENTS as s}
            <option value={s}>{s}</option>
          {/each}
        </select>
        <label>收敛（毫米，可正可负）</label>
        <input type="number" step="0.1" bind:value={deltaMm} />
        <button disabled={loading} on:click={submit}>提交（进入待认领）</button>
        {#if error}<p class="err">{error}</p>{/if}
      </section>
    {/if}
    <section>
      <table>
        <thead>
          <tr><th>编号</th><th>桩号</th><th>部位</th><th>收敛mm</th><th>状态</th><th>结论</th><th>说明</th></tr>
        </thead>
        <tbody>
          {#each logs as row}
            <tr>
              <td>{row.id}</td>
              <td>{row.chainage}</td>
              <td>{row.segment}</td>
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
      <h2>合成专页</h2>
      <p class="hint">
        勾选至少两笔同类（拱顶 / 边墙 / 注浆段）已办结单，先点「预览后台平均」，再点「生成合成单」。
        未办结单不能勾入；不同类别不能混入同一笔；平均值一律由后台计算并随合成流水一并记账。
      </p>
      <table>
        <thead>
          <tr><th>勾选</th><th>编号</th><th>桩号</th><th>部位</th><th>收敛mm</th><th>状态</th><th>结论</th></tr>
        </thead>
        <tbody>
          {#each logs as row}
            <tr>
              <td>
                <input
                  type="checkbox"
                  disabled={row.status !== "done"}
                  checked={selectedIds.includes(row.id)}
                  on:change={() => toggle(row.id)}
                />
              </td>
              <td>{row.id}</td>
              <td>{row.chainage}</td>
              <td>{row.segment}</td>
              <td>{row.delta_mm}</td>
              <td><span class="tag {row.status === 'pending' ? 'pending' : 'ok'}">{row.status === 'pending' ? '待认领' : '已办结'}</span></td>
              <td>
                {#if row.verdict}
                  <span class="tag {row.verdict === '合格' ? 'ok' : 'bad'}">{row.verdict}</span>
                {:else}—{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <div class="actions">
        <span class="hint">已勾 {selectedCount} 笔</span>
        <button disabled={loading || selectedCount === 0} on:click={previewMerge}>预览后台平均</button>
        {#if isWriter}
          <button disabled={loading || selectedCount === 0} on:click={generateMerge}>生成合成单</button>
        {:else}
          <button disabled title="巡检员仅可预览，不能代点生成">生成合成单（巡检员不可点）</button>
        {/if}
      </div>
      {#if mergeError}<p class="err">{mergeError}</p>{/if}
      {#if mergeNotice}<p class="notice">{mergeNotice}</p>{/if}
      {#if preview}
        <div class="preview">
          <p><strong>后台预览</strong>（未记账，仅试算）</p>
          <p>部位：{preview.segment}　笔数：{preview.count}　后台平均：{preview.average_mm} mm</p>
          <p>来源单：{preview.sources.map((s) => "#" + s.id).join("、")}</p>
        </div>
      {/if}
    </section>
    <section>
      <h2>合成流水</h2>
      <table>
        <thead>
          <tr><th>流水号</th><th>部位</th><th>平均mm</th><th>来源单号</th><th>新单号</th><th>经办</th><th>时间</th></tr>
        </thead>
        <tbody>
          {#each merges as m}
            <tr>
              <td>{m.id}</td>
              <td>{m.segment}</td>
              <td>{m.average_mm}</td>
              <td>{m.source_log_ids.join("、")}</td>
              <td>{m.result_log_id}</td>
              <td>{m.created_by}</td>
              <td>{m.created_at ? m.created_at.slice(0, 19).replace("T", " ") : "—"}</td>
            </tr>
          {:else}
            <tr><td colspan="7">暂无合成流水</td></tr>
          {/each}
        </tbody>
      </table>
    </section>
  {/if}
</main>
