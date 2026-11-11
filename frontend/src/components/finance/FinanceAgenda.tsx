"use client";

import { useEffect, useMemo, useState } from "react";
import { BusyLabel } from "@/components/PageLoader";
import { FinancePushToggle } from "@/components/finance/FinancePushToggle";
import { SvgCalendar, SvgPlus, SvgTrash } from "@/components/ui/svgs";
import {
  api,
  type FinanceCategoryOption,
  type FinanceEventItem,
  type FinanceEventPayload,
} from "@/lib/api";
import {
  addDays,
  formatDayLetter,
  formatMonthYear,
  formatTime,
  formatWeekday,
  getWeekDaysFor,
  sameDay,
  splitDateTime,
  startOfDay,
  toLocalDateTime,
  todayISODate,
} from "@/lib/finance";

const HOUR_PX = 52;
const START_HOUR = 8;
const END_HOUR = 19;

type Props = {
  events: FinanceEventItem[];
  categories: FinanceCategoryOption[];
  vapidPublicKey?: string | null;
  onChanged: () => void;
};

export function FinanceAgenda({ events, categories, vapidPublicKey, onChanged }: Props) {
  const [view, setView] = useState<"day" | "week">("day");
  const [selected, setSelected] = useState(() => startOfDay(new Date()));
  const [editing, setEditing] = useState<FinanceEventItem | "new" | null>(null);
  const today = startOfDay(new Date());
  const week = getWeekDaysFor(selected);

  const dayEvents = events.filter((event) => sameDay(new Date(event.starts_at), selected));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          {(["day", "week"] as const).map((id) => (
            <button
              key={id}
              type="button"
              className={`fin-chip ${view === id ? "active" : ""}`}
              onClick={() => setView(id)}
            >
              <SvgCalendar className="w-4 h-4" />
              {id === "day" ? "Dia" : "Semana"}
            </button>
          ))}
        </div>
        <button type="button" className="btn-primary !py-2 !px-4 text-sm" onClick={() => setEditing("new")}>
          <SvgPlus className="w-4 h-4" />
          Novo evento
        </button>
      </div>
      {vapidPublicKey ? <FinancePushToggle vapidPublicKey={vapidPublicKey} /> : null}

      <div className="glass-card p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2 min-w-0">
            <button
              type="button"
              className="btn-ghost !p-2"
              aria-label="Semana anterior"
              onClick={() => setSelected(addDays(selected, -7))}
            >
              ‹
            </button>
            <p className="font-semibold truncate">{formatMonthYear(selected)}</p>
            <button
              type="button"
              className="btn-ghost !p-2"
              aria-label="Próxima semana"
              onClick={() => setSelected(addDays(selected, 7))}
            >
              ›
            </button>
          </div>
          <button
            type="button"
            className={`fin-today ${sameDay(selected, today) ? "is-today" : ""}`}
            onClick={() => setSelected(today)}
            disabled={sameDay(selected, today)}
          >
            Hoje
          </button>
        </div>

        <div className="fin-day-strip">
          {week.map((day) => {
            const active = sameDay(day, selected);
            const isToday = sameDay(day, today);
            return (
              <button
                key={day.toISOString()}
                type="button"
                className={`fin-day-pill ${active ? "active" : ""} ${isToday && !active ? "today" : ""}`}
                onClick={() => {
                  setSelected(day);
                  setView("day");
                }}
              >
                <span className="fin-day-letter">{formatDayLetter(day)}</span>
                <span className="fin-day-num">{day.getDate()}</span>
              </button>
            );
          })}
        </div>

        {view === "day" ? (
          <DayTimeline events={dayEvents} selected={selected} onOpen={setEditing} />
        ) : (
          <WeekBoard
            week={week}
            today={today}
            events={events}
            onOpen={(event) => {
              setSelected(startOfDay(new Date(event.starts_at)));
              setEditing(event);
            }}
          />
        )}
      </div>

      {editing && (
        <EventModal
          event={editing === "new" ? null : editing}
          categories={categories}
          defaultDate={todayISODate(selected)}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function DayTimeline({
  events,
  selected,
  onOpen,
}: {
  events: FinanceEventItem[];
  selected: Date;
  onOpen: (event: FinanceEventItem) => void;
}) {
  const timed = events.filter((event) => !event.all_day);
  const allDay = events.filter((event) => event.all_day);
  let startHour = START_HOUR;
  let endHour = END_HOUR;
  timed.forEach((event) => {
    const d = new Date(event.starts_at);
    const endH = d.getHours() + Math.ceil(Math.max(event.duration_min, 30) / 60);
    if (d.getHours() < startHour) startHour = Math.max(6, d.getHours());
    if (endH > endHour) endHour = Math.min(22, endH);
  });
  const hours = Array.from({ length: Math.max(endHour - startHour, 1) }, (_, i) => startHour + i);
  const gridHeight = hours.length * HOUR_PX;
  const now = new Date();
  const showNow = sameDay(selected, startOfDay(now));
  const nowTop = ((now.getHours() - startHour) * 60 + now.getMinutes()) / 60 * HOUR_PX;

  useEffect(() => {
    const wrap = document.getElementById("fin-agenda-wrap");
    if (!wrap) return;
    const target = showNow ? Math.max(nowTop - 80, 0) : 0;
    wrap.scrollTop = target;
  }, [selected, showNow, nowTop]);

  return (
    <>
      {allDay.length > 0 && (
        <div className="fin-allday">
          {allDay.map((event) => (
            <button
              key={event.id}
              type="button"
              className="fin-allday-item"
              data-type={event.category}
              onClick={() => onOpen(event)}
            >
              {event.title}
            </button>
          ))}
        </div>
      )}
      <div className="fin-timeline-wrap" id="fin-agenda-wrap">
        <div className="fin-timeline" style={{ ["--hour-h" as string]: `${HOUR_PX}px` }}>
          <div className="fin-hours">
            {hours.map((hour) => (
              <span key={hour} className="fin-hour-label">
                {String(hour).padStart(2, "0")}:00
              </span>
            ))}
          </div>
          <div className="fin-grid" style={{ height: gridHeight }}>
            {hours.map((hour) => (
              <div key={hour} className="fin-grid-line" />
            ))}
            {showNow && nowTop >= 0 && nowTop <= gridHeight && (
              <div className="fin-now-line" style={{ top: nowTop }}>
                <span className="fin-now-dot" />
              </div>
            )}
            {timed.map((event) => {
              const d = new Date(event.starts_at);
              const top = ((d.getHours() - startHour) * 60 + d.getMinutes()) / 60 * HOUR_PX;
              const height = Math.max((Math.max(event.duration_min, 30) / 60) * HOUR_PX, 36);
              const end = new Date(d.getTime() + event.duration_min * 60000);
              return (
                <button
                  key={event.id}
                  type="button"
                  className="fin-event"
                  data-type={event.category}
                  style={{ top, height }}
                  onClick={() => onOpen(event)}
                >
                  <span className="fin-event-title">{event.title}</span>
                  <span className="fin-event-time">
                    {formatTime(event.starts_at)} – {formatTime(end.toISOString())}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        {events.length === 0 && (
          <p className="text-sm text-muted text-center py-8">Nenhum evento neste dia. Cadastre uma manutenção, dentista ou compromisso.</p>
        )}
      </div>
    </>
  );
}

function WeekBoard({
  week,
  today,
  events,
  onOpen,
}: {
  week: Date[];
  today: Date;
  events: FinanceEventItem[];
  onOpen: (event: FinanceEventItem) => void;
}) {
  return (
    <div className="fin-week">
      {week.map((day) => {
        const dayEvents = events.filter((event) => sameDay(new Date(event.starts_at), day));
        return (
          <div key={day.toISOString()} className={`fin-week-col ${sameDay(day, today) ? "today" : ""}`}>
            <p className="fin-week-label">{formatWeekday(day)}</p>
            <p className="fin-week-num">{day.getDate()}</p>
            {dayEvents.map((event) => (
              <button
                key={event.id}
                type="button"
                className="fin-week-event"
                data-type={event.category}
                onClick={() => onOpen(event)}
              >
                <strong>{event.title}</strong>
                <span>{event.all_day ? "Dia inteiro" : formatTime(event.starts_at)}</span>
              </button>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function EventModal({
  event,
  categories,
  defaultDate,
  onClose,
  onSaved,
}: {
  event: FinanceEventItem | null;
  categories: FinanceCategoryOption[];
  defaultDate: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const initial = useMemo(() => {
    if (!event) {
      return {
        title: "",
        category: categories[0]?.id || "pessoal",
        notes: "",
        date: defaultDate,
        time: "09:00",
        duration_min: 60,
        all_day: false,
      };
    }
    const split = splitDateTime(event.starts_at);
    return {
      title: event.title,
      category: event.category,
      notes: event.notes,
      date: split.date,
      time: split.time,
      duration_min: event.duration_min || 60,
      all_day: event.all_day,
    };
  }, [event, categories, defaultDate]);

  const [form, setForm] = useState(initial);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => setForm(initial), [initial]);

  const payload = (): FinanceEventPayload => ({
    title: form.title.trim(),
    category: form.category,
    notes: form.notes.trim(),
    starts_at: toLocalDateTime(form.date, form.all_day ? "00:00" : form.time),
    duration_min: form.all_day ? 0 : Number(form.duration_min) || 60,
    all_day: form.all_day,
  });

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (event) await api.financeUpdateEvent(event.id, payload());
      else await api.financeCreateEvent(payload());
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setLoading(false);
    }
  };

  const remove = async () => {
    if (!event) return;
    setLoading(true);
    setError("");
    try {
      await api.financeDeleteEvent(event.id);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível excluir");
      setLoading(false);
    }
  };

  return (
    <div className="fin-modal-backdrop" onClick={onClose} role="presentation">
      <form className="glass-card fin-modal" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <h2 className="text-lg font-semibold mb-4">{event ? "Editar evento" : "Novo evento"}</h2>
        <div className="space-y-4">
          <Field label="Título">
            <input
              required
              className="input-glass"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Dentista, manutenção do carro…"
            />
          </Field>
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Categoria">
              <select
                className="input-glass"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              >
                {categories.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Data">
              <input
                type="date"
                required
                className="input-glass"
                value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })}
              />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm text-secondary">
            <input
              type="checkbox"
              checked={form.all_day}
              onChange={(e) => setForm({ ...form, all_day: e.target.checked })}
            />
            Dia inteiro
          </label>
          {!form.all_day && (
            <div className="grid sm:grid-cols-2 gap-4">
              <Field label="Horário">
                <input
                  type="time"
                  required
                  className="input-glass"
                  value={form.time}
                  onChange={(e) => setForm({ ...form, time: e.target.value })}
                />
              </Field>
              <Field label="Duração (min)">
                <input
                  type="number"
                  min={15}
                  max={1440}
                  step={15}
                  className="input-glass"
                  value={form.duration_min}
                  onChange={(e) => setForm({ ...form, duration_min: Number(e.target.value) })}
                />
              </Field>
            </div>
          )}
          <Field label="Detalhes">
            <textarea
              className="input-glass min-h-[88px] resize-y"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Endereço, o que levar, observações…"
            />
          </Field>
          {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
        </div>
        <div className="flex flex-wrap justify-between gap-2 mt-6">
          {event ? (
            <button type="button" className="btn-ghost text-[var(--danger)]" onClick={remove} disabled={loading}>
              <SvgTrash className="w-4 h-4" />
              Excluir
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-2 ml-auto">
            <button type="button" className="btn-ghost" onClick={onClose}>
              Cancelar
            </button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? <BusyLabel>Salvando…</BusyLabel> : "Salvar"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs text-muted block mb-1.5">{label}</label>
      {children}
    </div>
  );
}
