"use strict";

const element = (id) => document.getElementById(id);
const byName = (form, name) => form.elements.namedItem(name);
const state = {session: null, ticket: null, meeting: null, rows: [], editing: null};

function notice(text, failed = false) {
  const output = element("status");
  output.textContent = text;
  output.classList.toggle("error", failed);
  output.hidden = !text;
}

async function request(path, method = "GET", body, token = state.session?.token ?? state.ticket?.token) {
  const headers = {Accept: "application/json"};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api${path}`, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Не удалось выполнить запрос.");
  return data;
}

async function run(operation, control) {
  if (control) control.disabled = true;
  notice("");
  try {
    await operation();
  } catch (error) {
    notice(error.message, true);
  } finally {
    if (control) control.disabled = false;
  }
}

function action(label, operation, style = "secondary") {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.className = style;
  button.addEventListener("click", () => run(operation, button));
  return button;
}

function showList(list, rows, empty) {
  list.replaceChildren();
  if (!rows.length) rows = [empty];
  for (const row of rows) {
    const item = document.createElement("li");
    item.append(row);
    list.append(item);
  }
}

function form(id, operation) {
  const target = element(id);
  target.addEventListener("submit", (event) => {
    event.preventDefault();
    run(() => operation(Object.fromEntries(new FormData(target)), target), event.submitter);
  });
}

function renderIdentity() {
  const role = state.session?.account.role;
  element("entry").hidden = Boolean(role || state.ticket);
  element("admin").hidden = role !== "администратор";
  element("host").hidden = role !== "организатор";
  element("guest").hidden = !state.ticket;
  element("logout").hidden = !role && !state.ticket;
  element("page-title").textContent = {
    администратор: "Управление платформой", организатор: "Встречи организатора",
  }[role] ?? (state.ticket ? "Участие в конференции" : "Подключение к конференции");
  element("identity").hidden = !role;
  element("identity").textContent = role ? state.session.account.email : "";
}

function localDate(value) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("ru-RU", {dateStyle: "medium", timeStyle: "short"}).format(date);
}

function fillEditor(meeting = null) {
  const editor = element("meeting-form");
  editor.reset();
  state.editing = meeting?.id ?? null;
  element("editor-title").textContent = meeting ? "Изменить встречу" : "Запланировать встречу";
  element("cancel-edit").hidden = !meeting;
  if (!meeting) return;
  for (const name of ["title", "description", "minutes"]) byName(editor, name).value = meeting[name];
  const date = new Date(meeting.starts_at);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  byName(editor, "starts_at").value = local.toISOString().slice(0, 16);
}

async function loadMeetings() {
  state.rows = await request("/meetings");
  const rows = state.rows.map((meeting) => action(
    `${meeting.title} · ${meeting.status} · ${localDate(meeting.starts_at)}`,
    () => selectMeeting(meeting.id),
  ));
  showList(element("meetings"), rows, "Встреч пока нет.");
}

async function selectMeeting(id) {
  state.meeting = id;
  const meeting = state.rows.find((item) => item.id === id);
  if (!meeting) return;
  const planned = meeting.status === "Запланирована";
  const live = meeting.status === "Идёт";
  element("details").hidden = false;
  element("meeting-title").textContent = meeting.title;
  element("meeting-state").textContent = `${meeting.status} · ${localDate(meeting.starts_at)} · ${meeting.minutes} мин`;
  element("meeting-description").textContent = meeting.description;
  const invite = new URL("/", window.location.origin);
  invite.searchParams.set("invite", meeting.invite);
  element("invite-line").hidden = !planned && !live;
  element("invite-link").href = invite.href;
  element("meeting-code").textContent = meeting.invite;
  const buttons = [];
  if (planned) buttons.push(action("Изменить встречу", () => fillEditor(meeting)));
  if (planned) buttons.push(action("Запустить", () => changeMeeting("start"), ""));
  if (planned) buttons.push(action("Отменить встречу", () => changeMeeting("cancel")));
  if (planned || live) buttons.push(action("Обновить приглашение", () => changeMeeting("renew")));
  if (live) buttons.push(action("Завершить встречу", () => changeMeeting("finish"), ""));
  if (meeting.status === "Завершена") buttons.push(action("Скачать CSV", downloadReport, ""));
  element("meeting-actions").replaceChildren(...buttons);
  element("queue-section").hidden = !planned && !live;
  element("room").hidden = !live;
  if (planned || live) await loadQueue();
  if (live) await loadRoom();
}

async function changeMeeting(name) {
  await request(`/meetings/${state.meeting}/actions`, "POST", {action: name});
  await loadMeetings();
  await selectMeeting(state.meeting);
}

function availableGuestActions(guest, meeting) {
  if (meeting !== "Идёт") return [];
  return {
    Ожидает: [["Допустить", "admit"], ["Отклонить", "reject"]],
    Допущен: [["Отозвать допуск", "kick"]],
    "Связь прервана": [["Отозвать допуск", "kick"]],
    "В комнате": [[guest.speaker ? "Снять право выступления" : "Дать право выступления", guest.speaker ? "speaker-off" : "speaker-on"], ["Удалить", "kick"]],
  }[guest.status] ?? [];
}

async function loadQueue() {
  const guests = await request(`/meetings/${state.meeting}/queue`);
  const meeting = state.rows.find((item) => item.id === state.meeting);
  const rows = guests.map((guest) => {
    const row = document.createElement("div");
    const buttons = document.createElement("div");
    buttons.className = "actions";
    for (const [label, name] of availableGuestActions(guest, meeting?.status)) {
      buttons.append(action(label, async () => {
        await request(`/meetings/${state.meeting}/guests/${guest.id}`, "PATCH", {action: name});
        await loadQueue();
        if (!element("room").hidden) await loadRoom();
      }));
    }
    row.append(`#${guest.id} · ${guest.name} · ${guest.status}`, buttons);
    return row;
  });
  showList(element("queue"), rows, "Заявок пока нет.");
}

async function loadGuest() {
  const base = `/meetings/${state.meeting}/guest`;
  const guest = await request(base);
  element("guest-state").textContent = `${guest.name} · ${guest.status}`;
  const buttons = [action("Проверить статус", loadGuest)];
  if (["Допущен", "Связь прервана"].includes(guest.status)) {
    buttons.push(action("Войти в комнату", () => connectGuest("join"), ""));
  }
  if (guest.status === "В комнате") buttons.push(action("Отключиться от комнаты", () => connectGuest("leave")));
  element("guest-actions").replaceChildren(...buttons);
  element("room").hidden = guest.status !== "В комнате";
  element("device").hidden = !guest.speaker;
  if (!element("room").hidden) await loadRoom();
}

async function connectGuest(name) {
  await request(`/meetings/${state.meeting}/guest/connection`, "POST", {action: name});
  await loadGuest();
}

async function loadRoom() {
  const base = `/meetings/${state.meeting}`;
  const roster = await request(base + "/room");
  const states = (microphone, camera) => `микрофон ${microphone ? "вкл." : "выкл."}, камера ${camera ? "вкл." : "выкл."}`;
  const label = `${roster.host} (организатор) · ${states(roster.host_microphone, roster.host_camera)}`;
  const guests = roster.guests.map((guest) => `${guest.name} · ${guest.speaker ? "выступает" : "слушает"} · ${states(guest.microphone, guest.camera)}`);
  showList(element("roster"), [label, ...guests], "Участников пока нет.");
  const presenter = roster.screen_owner === 0 ? roster.host : roster.guests.find((guest) => guest.id === roster.screen_owner)?.name;
  element("screen").textContent = presenter ? `Состояние показа: ${presenter}` : "Экран свободен.";
  const messages = await request(base + "/messages");
  showList(element("messages"), messages.map((message) => {
    const row = document.createElement("div");
    row.append(`${message.author}: ${message.text} `);
    if (state.session) row.append(action("Скрыть", async () => {
      await request(`${base}/messages/${message.id}`, "DELETE");
      await loadRoom();
    }));
    return row;
  }), "Сообщений пока нет.");
}

async function downloadReport() {
  const report = await request(`/meetings/${state.meeting}/attendance`);
  const url = URL.createObjectURL(new Blob([report.content], {type: "text/csv;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = report.file_name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

form("login", async (data, target) => {
  state.session = await request("/sessions", "POST", data);
  target.reset();
  renderIdentity();
  if (state.session.account.role === "организатор") await loadMeetings();
});
form("apply", async (data) => {
  state.ticket = await request("/guest-applications", "POST", data);
  state.meeting = state.ticket.meeting_id;
  renderIdentity();
  await loadGuest();
});
form("add-host", async (data, target) => {
  const account = await request("/accounts", "POST", data);
  target.reset();
  notice(`Запись ${account.email} создана.`);
});
form("block", async ({email, blocked}) => {
  const account = await request(`/accounts/${encodeURIComponent(email)}`, "PATCH", {blocked: blocked === "true"});
  notice(`${account.email} · ${account.blocked ? "доступ заблокирован" : "доступ восстановлен"}`);
});
form("meeting-form", async (data) => {
  data.minutes = Number(data.minutes);
  data.starts_at = new Date(data.starts_at).toISOString();
  const meeting = state.editing
    ? await request(`/meetings/${state.editing}`, "PUT", data)
    : await request("/meetings", "POST", data);
  fillEditor();
  await loadMeetings();
  await selectMeeting(meeting.id);
});
form("device", async ({device, enabled}) => {
  await request(`/meetings/${state.meeting}/room/device`, "PUT", {device, enabled: enabled === "true"});
  await loadRoom();
});
form("send", async (data, target) => {
  await request(`/meetings/${state.meeting}/messages`, "POST", data);
  target.reset();
  await loadRoom();
});
element("cancel-edit").addEventListener("click", () => fillEditor());
element("refresh-queue").addEventListener("click", (event) => run(loadQueue, event.currentTarget));
element("refresh-room").addEventListener("click", (event) => run(state.ticket ? loadGuest : loadRoom, event.currentTarget));
element("refresh-meetings").addEventListener("click", (event) => run(async () => {
  await loadMeetings();
  if (state.meeting !== null) await selectMeeting(state.meeting);
}, event.currentTarget));
element("logout").addEventListener("click", () => window.location.reload());
byName(element("apply"), "invite").value = new URLSearchParams(window.location.search).get("invite") ?? "";
