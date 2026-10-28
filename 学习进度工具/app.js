"use strict";
const $ = id => document.getElementById(id);
let state, weekIndex = 0, dayIndex = 0, dirty = false, saving = false, token;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function message(text, error = false) {
  $("message").textContent = text;
  $("message").className = error ? "error" : "";
}
function setDirty() {
  dirty = true;
  $("save-status").textContent = "有未保存的修改";
}
function allowNavigate() {
  return !saving && (!dirty || window.confirm("当前修改尚未保存。确定放弃这些修改吗？"));
}
function selectOptions(id, options, value) {
  $(id).replaceChildren(...options.map(v => {
    const option = element("option", v); option.value = v; return option;
  }));
  $(id).value = value;
}
function textFields(container, values) {
  $(container).replaceChildren();
  Object.entries(values).forEach(([key, value]) => {
    const label = element("label", key);
    const input = element("textarea");
    input.dataset.key = key;
    input.value = value;
    input.placeholder = key === "下次具体起点" ? "例如：继续看线程池队列满后的拒绝处理" : "记录你的理解、证据或待解决的问题…";
    label.append(input); $(container).append(label);
  });
}
function readFields(container) {
  return Object.fromEntries([...$(container).querySelectorAll("textarea")].map(input => [input.dataset.key, input.value]));
}
function render() {
  const week = state.weeks[weekIndex], day = week.days[dayIndex];
  $("total").textContent = `${state.summary.completed} / 60 天`;
  $("progress").value = state.summary.completed;
  $("hours").textContent = `累计 ${Number(state.summary.hours.toFixed(2))} 小时 · ${state.summary.status}`;
  $("week-title").textContent = week.title;
  $("weeks").replaceChildren(...state.weeks.map((w, i) => {
    const button = element("button", undefined, "week" + (i === weekIndex ? " active" : ""));
    button.type = "button";
    button.setAttribute("aria-current", i === weekIndex ? "step" : "false");
    button.append(element("span", String(i + 1).padStart(2, "0"), "num"), element("span", w.title.replace(/^第 \d+ 周 /, ""), "week-text"), element("span", `${w.summary.completed}/5`, "count"));
    button.onclick = () => { if (i !== weekIndex && allowNavigate()) { weekIndex = i; dayIndex = 0; render(); message(""); } };
    return button;
  }));
  $("days").replaceChildren(...week.days.map((d, i) => {
    const button = element("button", undefined, "day" + (i === dayIndex ? " active" : ""));
    button.type = "button";
    button.setAttribute("aria-pressed", String(i === dayIndex));
    button.append(element("strong", `第 ${i + 1} 天`), element("span", d.status));
    button.onclick = () => { if (i !== dayIndex && allowNavigate()) { dayIndex = i; render(); message(""); } };
    return button;
  }));
  $("day-label").textContent = `第 ${weekIndex + 1} 周 · 第 ${dayIndex + 1} 天`;
  $("day-title").textContent = day.title;
  $("day-status").textContent = day.status;
  selectOptions("status", state.statuses, day.status);
  selectOptions("level", state.levels, day.level);
  $("date").value = day.date;
  $("duration").value = day.hours ?? "";
  $("tasks").replaceChildren(...day.tasks.map(task => {
    const label = element("label", undefined, "task" + (task.done ? " done" : ""));
    const check = element("input"); check.type = "checkbox"; check.checked = task.done;
    label.append(check, element("span", task.text));
    check.onchange = () => { label.classList.toggle("done", check.checked); taskCount(); };
    return label;
  }));
  taskCount();
  textFields("records", day.records); textFields("review", week.review);
  $("references").replaceChildren(...week.references.map(ref => element("li", ref)));
  $("editor").hidden = false;
  dirty = false;
  $("save-status").textContent = "尚无未保存的修改";
}
function taskCount() {
  const checks = [...$("tasks").querySelectorAll("input")];
  $("task-count").textContent = `${checks.filter(c => c.checked).length} / ${checks.length} 项`;
}
async function load(initial = false) {
  try {
    const response = await fetch("/api/state");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    state = data; token = data.token;
    if (initial) {
      const firstWeek = state.weeks.findIndex(w => w.days.some(d => d.status !== "已完成"));
      weekIndex = firstWeek < 0 ? 0 : firstWeek;
      const firstDay = state.weeks[weekIndex].days.findIndex(d => d.status === "学习中" || d.status === "待复习");
      dayIndex = firstDay < 0 ? Math.max(0, state.weeks[weekIndex].days.findIndex(d => d.status !== "已完成")) : firstDay;
    }
    render(); message(initial ? "" : "已重新读取本地文档。");
  } catch (error) { message(`读取失败：${error.message}`, true); }
}
$("editor").addEventListener("input", setDirty);
$("status").addEventListener("change", () => { $("day-status").textContent = $("status").value; });
$("reload").onclick = () => { if (allowNavigate()) load(); };
$("editor").onsubmit = async event => {
  event.preventDefault();
  if (saving || !state) return;
  const payload = {
    revision: state.revision, week: state.weeks[weekIndex].id, day: dayIndex + 1,
    status: $("status").value, level: $("level").value, date: $("date").value,
    hours: $("duration").value === "" ? null : Number($("duration").value),
    checks: [...$("tasks").querySelectorAll("input")].map(c => c.checked),
    records: readFields("records"), review: readFields("review")
  };
  saving = true;
  [...$("editor").querySelectorAll("input,select,textarea,button")].forEach(n => { n.disabled = true; });
  $("save").textContent = "正在保存…";
  try {
    const response = await fetch("/api/save", {method: "POST", headers: {"Content-Type": "application/json", "X-Study-Token": token}, body: JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    state = data;
    render();
    $("save-status").textContent = "已保存到本地文档";
    message("保存成功：已同步每日记录、周状态和总进度，原文档已备份。");
  } catch (error) { message(`保存失败：${error.message}`, true); }
  finally {
    saving = false;
    [...$("editor").querySelectorAll("input,select,textarea,button")].forEach(n => { n.disabled = false; });
    $("save").textContent = "保存到学习文档";
  }
};
window.addEventListener("beforeunload", event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
load(true);
