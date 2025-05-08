

import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import pandas as pd
import io
import datetime

TOKEN = "MTM2Mjk4MDc5NTkxNjA5MTUzNA.GwR7Je.TTq9VxlMhSWouyIUk1tBMRmC_BqHDabsfc7-do"

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix="!", intents=intents)
tree = client.tree

# 전역 변수
pet_data = None
reborn_pet_data = None
old_pet_list = []

# -------------------- 유틸 함수 --------------------

def handle_nan(value):
    return "" if pd.isna(value) else value

def pet_type(name: str) -> str:
    normalized = name.strip().lower().replace(" ", "")  # 공백 제거 포함

    # 일반 페트 데이터 확인
    if pet_data is not None:
        match = pet_data[
            pet_data["이름"].astype(str).str.lower().str.replace(" ", "") == normalized
        ]
        if not match.empty:
            # 구펫 리스트 로드 후 이름 비교
            cleaned_old_list = [n.replace(" ", "") for n in old_pet_list]  # 리스트에서 공백 제거
            if normalized in cleaned_old_list:
                return "(구펫)"
            return "(신펫)"

    return "(미확인)"


def chunk_message(msg: str, limit: int = 1900) -> list:
    lines = msg.split("\n")
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current += "\n" + line if current else line
    if current:
        chunks.append(current)
    return chunks

def apply_range_filter(df, column, value_str, range_str):
    if not value_str:
        return df
    try:
        value_str = value_str.strip()
        if "-" in value_str:
            low, high = map(float, value_str.split("-"))
        elif value_str.startswith("+") or value_str.startswith("-"):
            base = df[column].mean()
            offset = float(value_str)
            low, high = base + offset - 0.01, base + offset + 0.01
        else:
            base = float(value_str)
            range_val = float(range_str) if range_str else 0.01
            low, high = base - range_val, base + range_val
        return df[(df[column] >= low) & (df[column] <= high)]
    except Exception:
        return df

# -------------------- 명령어 --------------------

@tree.command(name="엑셀업로드", description="엑셀 파일을 업로드합니다.")
async def upload_excel(interaction: discord.Interaction):
    global pet_data, reborn_pet_data, old_pet_list

    try:
        await interaction.response.defer(ephemeral=True)  # 첫 응답 예약
    except discord.NotFound:
        return

    # 최근 메시지에서 엑셀 파일 찾기
    async for msg in interaction.channel.history(limit=20):
        for file in msg.attachments:
            if file.filename.endswith(".xlsx"):
                print(f"[디버그] 엑셀 파일 업로드됨: {file.filename}")  # 디버그: 파일 업로드 확인

                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(file.url) as resp:
                            data = await resp.read()

                    # 엑셀 파일 로드
                    xls = pd.ExcelFile(io.BytesIO(data))
                    print(f"[디버그] 엑셀 파일 시트 이름들: {xls.sheet_names}")  # 디버그: 시트 이름 출력

                    # 시트 확인 및 로드
                    pet_data = xls.parse("일반") if "일반" in xls.sheet_names else None
                    reborn_pet_data = xls.parse("환생") if "환생" in xls.sheet_names else None
                    old_pet_df = xls.parse("구펫 리스트") if "구펫 리스트" in xls.sheet_names else None
                    
                    # 구펫 리스트 로드 확인
                    if old_pet_df is not None:
                        old_pet_list = (
                            old_pet_df.iloc[:, 0]
                            .dropna()
                            .map(str)
                            .str.strip()
                            .str.lower()
                            .tolist()
                        )
                        print(f"[디버그] 구펫 리스트 로드된 항목 수: {len(old_pet_list)}")  # 디버그: 구펫 리스트 항목 수

                    # 일반과 환생 페트 데이터 갯수 확인
                    g_count = len(pet_data) if pet_data is not None else 0
                    r_count = len(reborn_pet_data) if reborn_pet_data is not None else 0

                    # 업로드 완료 메시지
                    await interaction.followup.send(
                        f"✅ 엑셀 업로드 완료! (일반 {g_count}종, 환생 {r_count}종)", ephemeral=True
                    )
                    return

                except Exception as e:
                    await interaction.followup.send(f"❗ 엑셀 처리 중 오류 발생: {e}", ephemeral=True)
                    return

    # 파일을 찾을 수 없을 경우
    await interaction.followup.send("❗ 최근 메시지에서 엑셀 파일(.xlsx)을 찾을 수 없습니다.", ephemeral=True)


@tree.command(name="엑셀상태", description="엑셀 데이터가 잘 로드되었는지 확인합니다.")
async def check_excel(interaction: discord.Interaction):
    msg = []
    if pet_data is not None and not pet_data.empty:
        msg.append(f"✅ 일반 페트 {len(pet_data)}개 로드됨")
    else:
        msg.append("❌ 일반 페트 없음")

    if reborn_pet_data is not None and not reborn_pet_data.empty:
        msg.append(f"✅ 환생 페트 {len(reborn_pet_data)}개 로드됨")
    else:
        msg.append("❌ 환생 페트 없음")

    await interaction.response.send_message("\n".join(msg), ephemeral=True)

@tree.command(name="페트이름", description="일반 페트를 이름으로 검색합니다.")
@app_commands.describe(이름="검색할 페트 이름 (일부 입력 가능)")
async def search_normal_pet_by_name(interaction: discord.Interaction, 이름: str):
    if pet_data is None or pet_data.empty:
        await interaction.response.send_message("❗ 먼저 일반 페트 데이터를 엑셀로 업로드해 주세요.")
        return

    name = 이름.strip().lower()
    df = pet_data[pet_data['이름'].astype(str).str.lower().str.contains(name)]

    if df.empty:
        await interaction.response.send_message("❌ 해당 이름을 포함한 일반 페트를 찾을 수 없습니다.")
        return

    msg = ""
    for _, row in df.head(10).iterrows():
        이름 = row['이름']
        구분표시 = pet_type(이름)
        속성표시 = f"{handle_nan(row['속성1'])}" if not row['속성2'] else f"{handle_nan(row['속성1'])}/{handle_nan(row['속성2'])}"
        msg += f"📜 {이름} {구분표시} (속성: {속성표시})\n"
        msg += f"⚔️ 공격력: {round(float(row['공격력 성장률']), 3)}\n"
        msg += f"🛡️ 방어력: {round(float(row['방어력 성장률']), 3)}\n"
        msg += f"🏃 순발력: {round(float(row['순발력 성장률']), 3)}\n"
        msg += f"❤️ 체력: {round(float(row.get('체력 성장률', row.get('체력성장률'))), 3)}\n"
        msg += f"🌟 총 성장률: {round(float(row.get('총 성장률', 0)), 3)}\n"
        msg += f"📦 획득처: {handle_nan(row.get('획득처', '정보 없음'))}\n\n"

    # 메시지를 1900자 제한 내에서 나누기 위해 분할
    chunks = chunk_message(msg)

    # 첫 번째 응답을 send_message로 보내고, 나머지 응답은 followup.send로 처리
    await interaction.response.send_message(chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)

@tree.command(name="환생페트이름", description="환생 페트를 이름으로 검색합니다.")
@app_commands.describe(이름="검색할 환생 페트 이름 (일부 입력 가능)")
async def search_reborn_pet_by_name(interaction: discord.Interaction, 이름: str):
    if reborn_pet_data is None or reborn_pet_data.empty:
        await interaction.response.send_message("❗ 먼저 환생 페트 데이터를 엑셀로 업로드해 주세요.")
        return

    name = 이름.strip().lower()
    df = reborn_pet_data[reborn_pet_data['이름'].astype(str).str.lower().str.contains(name)]

    if df.empty:
        await interaction.response.send_message("❌ 해당 이름을 포함한 환생 페트를 찾을 수 없습니다.")
        return

    msg = ""
    for _, row in df.head(10).iterrows():
        이름 = row['이름']
        속성표시 = f"{handle_nan(row['속성1'])}" if not row['속성2'] else f"{handle_nan(row['속성1'])}/{handle_nan(row['속성2'])}"
        msg += f"📜 {이름} (환생) (속성: {속성표시})\n"
        msg += f"⚔️ 공격력: {round(float(row['공격력 성장률']), 3)}\n"
        msg += f"🛡️ 방어력: {round(float(row['방어력 성장률']), 3)}\n"
        msg += f"🏃 순발력: {round(float(row['순발력 성장률']), 3)}\n"
        msg += f"❤️ 체력: {round(float(row.get('체력 성장률', row.get('체력성장률'))), 3)}\n"
        msg += f"🌟 총 성장률: {round(float(row.get('총 성장률', 0)), 3)}\n"
        msg += f"📦 획득처: {handle_nan(row.get('획득처', '정보 없음'))}\n\n"

    # 메시지를 1900자 제한 내에서 나누기 위해 분할
    chunks = chunk_message(msg)

    # 첫 번째 응답을 send_message로 보내고, 나머지 응답은 followup.send로 처리
    await interaction.response.send_message(chunks[0])
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


@tree.command(name="페트비교", description="최소 2~5마리까지 일반/환생 페트를 이름으로 비교합니다.")
@app_commands.describe(
    이름1="첫 번째 페트", 이름2="두 번째 페트",
    이름3="세 번째 페트 (선택)", 이름4="네 번째 페트 (선택)", 이름5="다섯 번째 페트 (선택)"
)
async def compare_multiple_pets(interaction: discord.Interaction, 이름1: str, 이름2: str, 이름3: str = None, 이름4: str = None, 이름5: str = None):
    if (pet_data is None or pet_data.empty) and (reborn_pet_data is None or reborn_pet_data.empty):
        await interaction.response.send_message("❗ 먼저 엑셀 데이터를 업로드하세요.")
        return

    names = [이름1, 이름2, 이름3, 이름4, 이름5]
    names = [n.strip() for n in names if n]

    def find_pet(name):
        name = name.lower()
        for df in [pet_data, reborn_pet_data]:
            if df is not None:
                result = df[df["이름"].astype(str).str.lower() == name]
                if not result.empty:
                    return result.iloc[0]
        return None

    pets = []
    for name in names:
        pet = find_pet(name)
        if pet is None:
            await interaction.response.send_message(f"❌ '{name}' 페트를 찾을 수 없습니다.")
            return
        pets.append(pet)

    def get_attr(p, key, fallback=None):
        return round(float(p.get(key, p.get(fallback, 0))), 3)

    headers = ["항목"] + [p["이름"][:10] for p in pets]
    rows = [
        ["속성"] + [f"{handle_nan(p['속성1'])}/{handle_nan(p['속성2'])}" for p in pets],
        ["총성장률"] + [f"{get_attr(p, '총 성장률')}" for p in pets],
        ["공격력"] + [f"{get_attr(p, '공격력 성장률')}" for p in pets],
        ["방어력"] + [f"{get_attr(p, '방어력 성장률')}" for p in pets],
        ["순발력"] + [f"{get_attr(p, '순발력 성장률')}" for p in pets],
        ["체력"] + [f"{get_attr(p, '체력 성장률', '체력성장률')}" for p in pets],
    ]

    def format_table(headers, rows):
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        def format_row(row):
            return " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        lines = [format_row(headers)]
        lines.append("-+-".join("-" * w for w in col_widths))
        for row in rows:
            lines.append(format_row(row))
        return "```\n" + "\n".join(lines) + "\n```"

    result = format_table(headers, rows)
    await interaction.response.send_message("📊 **페트 비교 결과**\n" + result)

@tree.command(name="환생페트비교", description="최소 2~5마리까지 환생 페트를 이름으로 비교합니다.")
@app_commands.describe(
    이름1="첫 번째 환생 페트", 이름2="두 번째", 이름3="세 번째 (선택)", 이름4="네 번째 (선택)", 이름5="다섯 번째 (선택)"
)
async def compare_reborn_pets(interaction: discord.Interaction, 이름1: str, 이름2: str, 이름3: str = None, 이름4: str = None, 이름5: str = None):
    if reborn_pet_data is None or reborn_pet_data.empty:
        await interaction.response.send_message("❗ 환생 페트 데이터가 없습니다.")
        return

    names = [이름1, 이름2, 이름3, 이름4, 이름5]
    names = [n.strip() for n in names if n]

    def find_pet(name):
        name = name.lower()
        result = reborn_pet_data[reborn_pet_data["이름"].astype(str).str.lower() == name]
        return result.iloc[0] if not result.empty else None

    pets = []
    for name in names:
        pet = find_pet(name)
        if pet is None:
            await interaction.response.send_message(f"❌ '{name}' 환생 페트를 찾을 수 없습니다.")
            return
        pets.append(pet)

    def get_attr(p, key, fallback=None):
        return round(float(p.get(key, p.get(fallback, 0))), 3)

    headers = ["항목"] + [p["이름"][:10] for p in pets]
    rows = [
        ["속성"] + [f"{handle_nan(p['속성1'])}/{handle_nan(p['속성2'])}" for p in pets],
        ["총성장률"] + [f"{get_attr(p, '총 성장률')}" for p in pets],
        ["공격력"] + [f"{get_attr(p, '공격력 성장률')}" for p in pets],
        ["방어력"] + [f"{get_attr(p, '방어력 성장률')}" for p in pets],
        ["순발력"] + [f"{get_attr(p, '순발력 성장률')}" for p in pets],
        ["체력"] + [f"{get_attr(p, '체력 성장률', '체력성장률')}" for p in pets],
    ]

    def format_table(headers, rows):
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        def format_row(row):
            return " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        lines = [format_row(headers)]
        lines.append("-+-".join("-" * w for w in col_widths))
        for row in rows:
            lines.append(format_row(row))
        return "```\n" + "\n".join(lines) + "\n```"

    result = format_table(headers, rows)
    await interaction.response.send_message("📊 **환생 페트 비교 결과**\n" + result)


@tree.command(name="페트확장검색", description="조건을 선택해 일반 페트를 검색합니다.")
@app_commands.describe(
    공격력="예: 0.5 / +0.03 / 0.4-0.6",
    공격력범위="기준값 ± 범위 (예: 0.05)",
    방어력="예: 0.4 / +0.02 / 0.35-0.45",
    방어력범위="기준값 ± 범위 (예: 0.03)",
    순발력="예: 0.3 / -0.01 / 0.25-0.35",
    순발력범위="기준값 ± 범위 (예: 0.02)",
    체력="예: 0.6 / +0.03 / 0.55-0.65",
    체력범위="기준값 ± 범위 (예: 0.03)",
    총성장률="예: 1.8 / +0.1 / 1.7-1.9",
    총성장률범위="기준값 ± 범위 (예: 0.1)",
    속성1="속성1 (예: 불)",
    속성2="속성2 (예: 물)",
    구분="전체 / 구펫 / 신펫",
    출력갯수="출력할 페트 수 (기본값: 10)"
)
async def search_normal_pet_advanced(
    interaction: discord.Interaction,
    공격력: str = None, 공격력범위: str = None,
    방어력: str = None, 방어력범위: str = None,
    순발력: str = None, 순발력범위: str = None,
    체력: str = None, 체력범위: str = None,
    총성장률: str = None, 총성장률범위: str = None,
    속성1: str = None, 속성2: str = None,
    구분: str = "전체", 출력갯수: int = 10
):
    if pet_data is None or pet_data.empty:
        await interaction.response.send_message("❗ 먼저 일반 페트 데이터를 엑셀로 업로드해 주세요.")
        return

    df = pet_data.copy()
    df = apply_range_filter(df, '공격력 성장률', 공격력, 공격력범위)
    df = apply_range_filter(df, '방어력 성장률', 방어력, 방어력범위)
    df = apply_range_filter(df, '순발력 성장률', 순발력, 순발력범위)
    df = apply_range_filter(df, '체력 성장률', 체력, 체력범위)
    df = apply_range_filter(df, '총 성장률', 총성장률, 총성장률범위)

    if 속성1:
        df = df[ 
            df['속성1'].astype(str).str.contains(속성1) |
            df['속성2'].astype(str).str.contains(속성1)
        ]
    if 속성2:
        df = df[ 
            df['속성1'].astype(str).str.contains(속성2) |
            df['속성2'].astype(str).str.contains(속성2)
        ]

    if 구분 == "구펫":
        df = df[df['이름'].apply(lambda n: pet_type(n) == "(구펫)")]
    elif 구분 == "신펫":
        df = df[df['이름'].apply(lambda n: pet_type(n) == "(신펫)")]

    if df.empty:
        await interaction.response.send_message("❌ 조건에 맞는 일반 페트가 없습니다.")
        return

    sort_keys = [k for k in ['공격력 성장률', '방어력 성장률', '순발력 성장률', '체력 성장률', '총 성장률'] if locals()[k.split()[0]]]
    if sort_keys:
        df = df.sort_values(by=sort_keys, ascending=[False] * len(sort_keys))

    total_results = len(df)
    df = df.head(출력갯수)

    # 페트 정보를 한 메시지 블록으로 나누어서 출력
    pet_blocks = []
    for _, row in df.iterrows():
        이름 = row['이름']
        구분표시 = pet_type(이름)
        속성표시 = f"{handle_nan(row['속성1'])}" if not row['속성2'] else f"{handle_nan(row['속성1'])}/{handle_nan(row['속성2'])}"

        block = f"📜 {이름} {구분표시} (속성: {속성표시})\n"
        block += f"⚔️ 공격력: {round(float(row['공격력 성장률']), 3)}\n"
        block += f"🛡️ 방어력: {round(float(row['방어력 성장률']), 3)}\n"
        block += f"🏃 순발력: {round(float(row['순발력 성장률']), 3)}\n"
        block += f"❤️ 체력: {round(float(row.get('체력 성장률', row.get('체력성장률'))), 3)}\n"
        block += f"🌟 총 성장률: {round(float(row.get('총 성장률', 0)), 3)}\n"
        block += f"📦 획득처: {handle_nan(row.get('획득처', '정보 없음'))}\n"
        pet_blocks.append(block)

    # 메시지 분할 (2000자 제한에 맞게 나누기)
    messages = []
    current = f"전체 결과 {total_results}개 중 상위 {출력갯수}개를 보여드립니다.\n\n"
    for block in pet_blocks:
        if len(current) + len(block) > 2000:  # 2000자 초과 시 새로운 메시지로 나누기
            messages.append(current)
            current = block
        else:
            current += "\n" + block
    if current:
        messages.append(current)

    # 메시지 보내기
    await interaction.response.send_message(messages[0])
    for msg in messages[1:]:
        await interaction.followup.send(msg)

#환생페트확장
@tree.command(name="환생페트확장검색", description="조건을 선택해 환생 페트를 검색합니다.")
@app_commands.describe(
    공격력="예: 0.5 / +0.03 / 0.4-0.6",
    공격력범위="기준값 ± 범위 (예: 0.05)",
    방어력="예: 0.4 / +0.02 / 0.35-0.45",
    방어력범위="기준값 ± 범위 (예: 0.03)",
    순발력="예: 0.3 / -0.01 / 0.25-0.35",
    순발력범위="기준값 ± 범위 (예: 0.02)",
    체력="예: 0.6 / +0.03 / 0.55-0.65",
    체력범위="기준값 ± 범위 (예: 0.03)",
    총성장률="예: 1.8 / +0.1 / 1.7-1.9",
    총성장률범위="기준값 ± 범위 (예: 0.1)",
    속성1="속성1 (예: 불)",
    속성2="속성2 (예: 물)",
    출력갯수="출력할 환생 페트 수 (기본값: 10)"
)
async def search_reborn_pet_advanced(
    interaction: discord.Interaction,
    공격력: str = None, 공격력범위: str = None,
    방어력: str = None, 방어력범위: str = None,
    순발력: str = None, 순발력범위: str = None,
    체력: str = None, 체력범위: str = None,
    총성장률: str = None, 총성장률범위: str = None,
    속성1: str = None, 속성2: str = None,
    출력갯수: int = 10
):
    if reborn_pet_data is None or reborn_pet_data.empty:
        await interaction.response.send_message("❗ 먼저 환생 페트 데이터를 엑셀로 업로드해 주세요.")
        return

    df = reborn_pet_data.copy()
    df = apply_range_filter(df, '공격력 성장률', 공격력, 공격력범위)
    df = apply_range_filter(df, '방어력 성장률', 방어력, 방어력범위)
    df = apply_range_filter(df, '순발력 성장률', 순발력, 순발력범위)
    df = apply_range_filter(df, '체력 성장률', 체력, 체력범위)
    df = apply_range_filter(df, '총 성장률', 총성장률, 총성장률범위)

    if 속성1:
        df = df[ 
            df['속성1'].astype(str).str.contains(속성1) |
            df['속성2'].astype(str).str.contains(속성1)
        ]
    if 속성2:
        df = df[ 
            df['속성1'].astype(str).str.contains(속성2) |
            df['속성2'].astype(str).str.contains(속성2)
        ]

    if df.empty:
        await interaction.response.send_message("❌ 조건에 맞는 환생 페트가 없습니다.")
        return

    sort_keys = [k for k in ['공격력 성장률', '방어력 성장률', '순발력 성장률', '체력 성장률', '총 성장률'] if locals()[k.split()[0]]]
    if sort_keys:
        df = df.sort_values(by=sort_keys, ascending=[False] * len(sort_keys))

    total_results = len(df)
    df = df.head(출력갯수)

    # 페트 정보를 한 메시지 블록으로 나누어서 출력
    pet_blocks = []
    for _, row in df.iterrows():
        이름 = row['이름']
        속성표시 = f"{handle_nan(row['속성1'])}" if not row['속성2'] else f"{handle_nan(row['속성1'])}/{handle_nan(row['속성2'])}"

        block = f"📜 {이름} (환생) (속성: {속성표시})\n"
        block += f"⚔️ 공격력: {round(float(row['공격력 성장률']), 3)}\n"
        block += f"🛡️ 방어력: {round(float(row['방어력 성장률']), 3)}\n"
        block += f"🏃 순발력: {round(float(row['순발력 성장률']), 3)}\n"
        block += f"❤️ 체력: {round(float(row.get('체력 성장률', row.get('체력성장률'))), 3)}\n"
        block += f"🌟 총 성장률: {round(float(row.get('총 성장률', 0)), 3)}\n"
        block += f"📦 획득처: {handle_nan(row.get('획득처', '정보 없음'))}\n"
        pet_blocks.append(block)

    # 메시지 분할 (2000자 제한에 맞게 나누기)
    messages = []
    current = f"전체 결과 {total_results}개 중 상위 {출력갯수}개 환생 페트를 보여드립니다.\n\n"
    for block in pet_blocks:
        if len(current) + len(block) > 2000:  # 2000자 초과 시 새로운 메시지로 나누기
            messages.append(current)
            current = block
        else:
            current += "\n" + block
    if current:
        messages.append(current)

    # 메시지 보내기
    await interaction.response.send_message(messages[0])
    for msg in messages[1:]:
        await interaction.followup.send(msg)



@client.event
async def on_ready():
    await tree.sync()
    print("✅ 글로벌 명령어 동기화 완료")
    print(f"✅ 봇 로그인됨: {client.user}")

client.run(TOKEN)
