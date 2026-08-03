import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import io
import re

# ==============================================================================
# НАСТРОЙКА СТРАНИЦЫ
# ==============================================================================
st.set_page_config(page_title="Сравнение периодов клиники", layout="wide")

st.markdown("""
    <style>
    .kpi-card-compare {
        flex: 1; min-width: 140px; background: #FFFFFF; border-radius: 6px; padding: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-top: 1px solid #EAEAEA;
        border-right: 1px solid #EAEAEA; border-bottom: 1px solid #EAEAEA;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Сравнение периодов: Загруженность докторов")
st.write("Загрузите два Excel-файла для сравнения базового и текущего периодов.")

col_upl1, col_upl2 = st.columns(2)
with col_upl1:
    uploaded_past = st.file_uploader("📥 Базовый (прошлый) период", type=["xlsx"], key="past")
with col_upl2:
    uploaded_curr = st.file_uploader("📥 Текущий (отчетный) период", type=["xlsx"], key="curr")

# ==============================================================================
# ФУНКЦИЯ ОБРАБОТКИ
# ==============================================================================
def clean_and_prepare_period(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    df_all = pd.read_excel(io.BytesIO(file_bytes), sheet_name=1, header=None)

    # Извлечение дат — гарантированно преобразуем каждую ячейку в строку
    raw_header_text = " ".join(str(v) for v in df_all.iloc[:5].values.flatten() if pd.notna(v))
    found_dates = re.findall(r'\d{2}\.\d{2}\.\d{4}', raw_header_text)
    dates_range = f"{found_dates[0]} - {found_dates[1]}" if len(found_dates) >= 2 else "Не определен"

    # Поиск строки заголовков
    header_row_index = None
    for idx, row in df_all.iterrows():
        row_vals = [str(v).lower() for v in row.values if pd.notna(v)]
        if any('специализация' in s for s in row_vals):
            header_row_index = idx
            break

    if header_row_index is None:
        raise ValueError("Не удалось найти строку заголовков в файле.")

    # Очистка
    df_clean = df_all.iloc[header_row_index + 1:].copy()
    df_clean.columns = df_all.iloc[header_row_index].astype(str).str.replace('~000', '', regex=False).str.strip()

    for col in ['Табель', 'Занято записями', 'Дошло пациентов']:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0)

    return df_clean, dates_range

# ==============================================================================
# ОБРАБОТКА И ВИЗУАЛИЗАЦИЯ
# ==============================================================================
if uploaded_past is not None and uploaded_curr is not None:
    try:
        df_past, date_past_str = clean_and_prepare_period(uploaded_past)
        df_curr, date_curr_str = clean_and_prepare_period(uploaded_curr)

        # --- Агрегация ---
        past_agg = df_past.groupby('Специализация')[['Табель', 'Занято записями', 'Дошло пациентов']].sum()
        curr_agg = df_curr.groupby('Специализация')[['Табель', 'Занято записями', 'Дошло пациентов']].sum()

        compare_df = curr_agg.merge(past_agg, on='Специализация', suffixes=('_Текущий', '_Прошлый'), how='outer').fillna(0)

        compare_df['Загрузка %_Прошлый'] = (compare_df['Занято записями_Прошлый'] / compare_df['Табель_Прошлый'].clip(lower=1) * 100).round(1)
        compare_df['Загрузка %_Текущий'] = (compare_df['Занято записями_Текущий'] / compare_df['Табель_Текущий'].clip(lower=1) * 100).round(1)

        past_losses = compare_df['Занято записями_Прошлый'] - compare_df['Дошло пациентов_Прошлый']
        curr_losses = compare_df['Занято записями_Текущий'] - compare_df['Дошло пациентов_Текущий']
        compare_df['Неявки %_Прошлый'] = (past_losses / compare_df['Занято записями_Прошлый'].clip(lower=1) * 100).round(1)
        compare_df['Неявки %_Текущий'] = (curr_losses / compare_df['Занято записями_Текущий'].clip(lower=1) * 100).round(1)

        compare_df['Δ Загрузка % (п.п.)'] = (compare_df['Загрузка %_Текущий'] - compare_df['Загрузка %_Прошлый']).round(1)
        compare_df['Δ Неявки % (п.п.)'] = (compare_df['Неявки %_Текущий'] - compare_df['Неявки %_Прошлый']).round(1)
        compare_df['Δ Часы записи (ч)'] = (compare_df['Занято записями_Текущий'] - compare_df['Занято записями_Прошлый']).round(1)
        compare_df['Δ Отработанные записи (пац)'] = (compare_df['Дошло пациентов_Текущий'] - compare_df['Дошло пациентов_Прошлый']).round(1)

        final_view = compare_df[[
            'Табель_Прошлый', 'Табель_Текущий',
            'Загрузка %_Прошлый', 'Загрузка %_Текущий', 'Δ Загрузка % (п.п.)',
            'Неявки %_Прошлый', 'Неявки %_Текущий', 'Δ Неявки % (п.п.)',
            'Занято записями_Прошлый', 'Занято записями_Текущий', 'Δ Часы записи (ч)',
            'Дошло пациентов_Прошлый', 'Дошло пациентов_Текущий', 'Δ Отработанные записи (пац)'
        ]].sort_values('Δ Загрузка % (п.п.)', ascending=False)

        # --- KPI расчеты ---
        total_past_tabel = df_past['Табель'].sum()
        total_curr_tabel = df_curr['Табель'].sum()
        diff_tabel = total_curr_tabel - total_past_tabel

        total_past_tab = df_past['Занято записями'].sum()
        total_curr_tab = df_curr['Занято записями'].sum()
        diff_tab = total_curr_tab - total_past_tab

        total_past_idle = total_past_tabel - total_past_tab
        total_curr_idle = total_curr_tabel - total_curr_tab
        diff_idle = total_curr_idle - total_past_idle

        total_past_ok = df_past['Дошло пациентов'].sum()
        total_curr_ok = df_curr['Дошло пациентов'].sum()
        diff_ok = total_curr_ok - total_past_ok

        avg_past_load = (total_past_tab / total_past_tabel * 100) if total_past_tabel > 0 else 0
        avg_curr_load = (total_curr_tab / total_curr_tabel * 100) if total_curr_tabel > 0 else 0
        diff_load = avg_curr_load - avg_past_load

        total_past_lost = total_past_tab - total_past_ok
        total_curr_lost = total_curr_tab - total_curr_ok

        avg_past_fail = (total_past_lost / total_past_tab * 100) if total_past_tab > 0 else 0
        avg_curr_fail = (total_curr_lost / total_curr_tab * 100) if total_curr_tab > 0 else 0
        diff_fail = avg_curr_fail - avg_past_fail

        def get_badge(value, is_inverse=False):
            if abs(value) < 0.05:
                return f'<span style="color: #6C757D; font-weight: bold;">0.0</span>'
            is_positive_change = value > 0
            is_good = is_positive_change if not is_inverse else not is_positive_change
            color = "#00A896" if is_good else "#D62828"
            sign = "+" if is_positive_change else ""
            arrow = "▲" if is_positive_change else "▼"
            return f'<span style="color: {color}; font-weight: bold;">{arrow} {sign}{value:,.1f}</span>'

        # --- Шапка ---
        st.markdown(f"""
        <div style="font-family: Arial, sans-serif; margin-bottom: 20px; padding: 10px 0; border-bottom: 2px solid #f0f2f5;">
            <span style="font-size: 20px; font-weight: bold; color: #2D3748;">📊 ИТОГОВЫЙ БАЛАНС ЭФФЕКТИВНОСТИ</span>
            <div style="font-size: 14px; color: #2D3748; margin-top: 8px;">
                Сравнение периодов: <b>Было: {date_past_str}</b> vs <b>Стало: {date_curr_str}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # --- KPI карточки ---
        kpi_html = f"""
        <div style="display: flex; gap: 10px; font-family: 'Segoe UI', sans-serif; margin-bottom: 25px; flex-wrap: wrap;">
            <div class="kpi-card-compare" style="border-left: 5px solid #005F73;">
                <div style="color: #8C757D; font-size: 11px; font-weight: 600; text-transform: uppercase;">Часов по табелю:</div>
                <div style="font-size: 22px; font-weight: 700; color: #2B2D42; margin: 5px 0;">{total_curr_tabel:,.1f} ч</div>
                <div style="font-size: 12px; color: #4A4A4A;">Было: {total_past_tabel:,.1f} ч {get_badge(diff_tabel)}</div>
            </div>
            <div class="kpi-card-compare" style="border-left: 5px solid #805F73;">
                <div style="color: #8C757D; font-size: 11px; font-weight: 600; text-transform: uppercase;">Часов записи:</div>
                <div style="font-size: 22px; font-weight: 700; color: #2B2D42; margin: 5px 0;">{total_curr_tab:,.1f} ч</div>
                <div style="font-size: 12px; color: #4A4A4A;">Было: {total_past_tab:,.1f} ч {get_badge(diff_tab)}</div>
            </div>
            <div class="kpi-card-compare" style="border-left: 5px solid #E9C46A;">
                <div style="color: #8C757D; font-size: 11px; font-weight: 600; text-transform: uppercase;">Незанятое время:</div>
                <div style="font-size: 22px; font-weight: 700; color: #2B2D42; margin: 5px 0;">{total_curr_idle:,.1f} ч</div>
                <div style="font-size: 12px; color: #4A4A4A;">Было: {total_past_idle:,.1f} ч {get_badge(diff_idle, is_inverse=True)}</div>
            </div>
            <div class="kpi-card-compare" style="border-left: 5px solid #F4A261;">
                <div style="color: #8C757D; font-size: 11px; font-weight: 600; text-transform: uppercase;">Загрузка клиники:</div>
                <div style="font-size: 22px; font-weight: 700; color: #2B2D42; margin: 5px 0;">{avg_curr_load:,.1f}%</div>
                <div style="font-size: 12px; color: #4A4A4A;">Было: {avg_past_load:,.1f}% {get_badge(diff_load)}</div>
            </div>
            <div class="kpi-card-compare" style="border-left: 5px solid #439D8D;">
                <div style="color: #8C757D; font-size: 11px; font-weight: 600; text-transform: uppercase;">Дошло пациентов:</div>
                <div style="font-size: 22px; font-weight: 700; color: #2B2D42; margin: 5px 0;">{total_curr_ok:,.1f} ч</div>
                <div style="font-size: 12px; color: #4A4A4A;">Было: {total_past_ok:,.1f} ч {get_badge(diff_ok)}</div>
            </div>
            <div class="kpi-card-compare" style="border-left: 5px solid #E76F51;">
                <div style="color: #8C757D; font-size: 11px; font-weight: 600; text-transform: uppercase;">Доля неявок:</div>
                <div style="font-size: 22px; font-weight: 700; color: #2B2D42; margin: 5px 0;">{avg_curr_fail:,.1f}%</div>
                <div style="font-size: 12px; color: #4A4A4A;">Было: {avg_past_fail:,.1f}% {get_badge(diff_fail, is_inverse=True)}</div>
            </div>
        </div>
        """
        st.markdown(kpi_html, unsafe_allow_html=True)

        # --- Сводная таблица ---
        with st.expander("📋 Развернуть сводную таблицу сравнения", expanded=False):
            st.dataframe(final_view.reset_index(), use_container_width=True)

        # --- Подготовка графиков ---
        past_grouped = df_past.groupby('Специализация', as_index=False)[['Табель', 'Занято записями', 'Дошло пациентов']].sum()
        curr_grouped = df_curr.groupby('Специализация', as_index=False)[['Табель', 'Занято записями', 'Дошло пациентов']].sum()

        past_grouped['Загрузка %'] = (past_grouped['Занято записями'] / past_grouped['Табель'] * 100).fillna(0).round(1)
        past_grouped['Потери %'] = ((past_grouped['Занято записями'] - past_grouped['Дошло пациентов']) / past_grouped['Занято записями'] * 100).fillna(0).round(1)
        curr_grouped['Загрузка %'] = (curr_grouped['Занято записями'] / curr_grouped['Табель'] * 100).fillna(0).round(1)
        curr_grouped['Потери %'] = ((curr_grouped['Занято записями'] - curr_grouped['Дошло пациентов']) / curr_grouped['Занято записями'] * 100).fillna(0).round(1)

        def create_melted_df(df_p, df_c, metric_col, value_name):
            p_sub = df_p[['Специализация', metric_col]].rename(columns={metric_col: 'Прошлый период (Было)'})
            c_sub = df_c[['Специализация', metric_col]].rename(columns={metric_col: 'Текущий период (Стало)'})
            merged = pd.merge(p_sub, c_sub, on='Специализация', how='outer').fillna(0)
            merged = merged.sort_values(by='Текущий период (Стало)', ascending=True)
            return merged.melt(
                id_vars='Специализация',
                value_vars=['Прошлый период (Было)', 'Текущий период (Стало)'],
                var_name='Период',
                value_name=value_name
            )

        df_melted_tabel = create_melted_df(past_grouped, curr_grouped, 'Табель', 'Часы')
        df_melted_zapisi = create_melted_df(past_grouped, curr_grouped, 'Занято записями', 'Часы')
        df_melted_load = create_melted_df(past_grouped, curr_grouped, 'Загрузка %', 'Проценты')
        df_melted_patients = create_melted_df(past_grouped, curr_grouped, 'Дошло пациентов', 'Часы')
        df_melted_losses = create_melted_df(past_grouped, curr_grouped, 'Потери %', 'Проценты')

        style_colors = {'Прошлый период (Было)': '#e8b833', 'Текущий период (Стало)': '#3a1d91'}
        style_layout = dict(
            template="plotly_white", height=700,
            margin=dict(t=60, b=40, l=150, r=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis={'categoryorder': 'trace'},
            bargap=0.025,        # ← меньше = полосы толще
            bargroupgap=0.005    # ← меньше = столбики внутри группы толще
        )

        # --- График 1 ---
        st.subheader("1. Сравнение выделенного времени по табелю (в часах)")
        p1 = px.bar(df_melted_tabel, x='Часы', y='Специализация', color='Период', barmode='group', orientation='h', color_discrete_map=style_colors)
        p1.update_layout(xaxis_title="Выделено часов по табелю", yaxis_title="Специализация", **style_layout)
        p1.update_traces(hovertemplate="<b>%{y}</b><br>Табель: %{x:.1f} ч<extra></extra>", texttemplate="%{x:.1f} ч", textposition="outside")
        st.plotly_chart(p1, use_container_width=True)

        # --- График 2 ---
        st.subheader("2. Сравнение объемов: Часы записи пациентов")
        p2 = px.bar(df_melted_zapisi, x='Часы', y='Специализация', color='Период', barmode='group', orientation='h', color_discrete_map=style_colors)
        p2.update_layout(xaxis_title="Часы записи пациентов", yaxis_title="Специализация", **style_layout)
        p2.update_traces(hovertemplate="<b>%{y}</b><br>Занято записями: %{x:.1f} ч<extra></extra>", texttemplate="%{x:.1f} ч", textposition="outside")
        st.plotly_chart(p2, use_container_width=True)

        # --- График 3 ---
        st.subheader("3. Сравнение заполненности расписания по периодам (Загрузка в %)")
        p3 = px.bar(df_melted_load, x='Проценты', y='Специализация', color='Период', barmode='group', orientation='h', color_discrete_map=style_colors)
        p3.update_layout(xaxis_title="Загрузка расписания (%)", yaxis_title="Специализация", **style_layout)
        p3.update_traces(hovertemplate="<b>%{y}</b><br>Загрузка: %{x:.1f}%<extra></extra>", texttemplate="%{x:.1f}%", textposition="outside")
        st.plotly_chart(p3, use_container_width=True)

        # --- График 4 ---
        st.subheader("4. Сравнение дошедших пациентов (в часах)")
        p4 = px.bar(df_melted_patients, x='Часы', y='Специализация', color='Период', barmode='group', orientation='h', color_discrete_map=style_colors)
        p4.update_layout(xaxis_title="Фактически осуществлено приемов", yaxis_title="Специализация", **style_layout)
        p4.update_traces(hovertemplate="<b>%{y}</b><br>Дошло пациентов: %{x:.1f} ч<extra></extra>", texttemplate="%{x:.1f} ч", textposition="outside")
        st.plotly_chart(p4, use_container_width=True)

        # --- График 5 ---
        st.subheader("5. Сравнение потерь из-за неявок пациентов (Недошедшие в %)")
        p5 = px.bar(df_melted_losses, x='Проценты', y='Специализация', color='Период', barmode='group', orientation='h', color_discrete_map=style_colors)
        p5.update_layout(xaxis_title="Доля недошедших пациентов (%)", yaxis_title="Специализация", **style_layout)
        p5.update_traces(hovertemplate="<b>%{y}</b><br>Потери: %{x:.1f}%<extra></extra>", texttemplate="%{x:.1f}%", textposition="outside")
        st.plotly_chart(p5, use_container_width=True)

    
    except Exception as e:
        st.error(f"❌ Ошибка при обработке файлов: {e}")
        st.exception(e)
