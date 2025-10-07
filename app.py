import streamlit as st
import gspread
import pandas as pd
import random
import time

# 設定頁面標題和佈局
st.set_page_config(
    page_title="綜合管理應用程式",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 從 Streamlit secrets 讀取 Google 服務帳號憑證
try:
    creds = st.secrets["gcp_service_account"]
    gc = gspread.service_account_from_dict(creds)
except Exception as e:
    st.error(f"無法連接到 Google Sheets。請檢查 .streamlit/secrets.toml 檔案和服務帳號權限。錯誤：{e}")
    st.stop()

def get_points_sheet():
    """連接並取得會員點數管理的 Google Sheet 資料 (包含登入資訊)。"""
    try:
        # 假設 sheet1 包含 暱稱, 點數, 帳號, 密碼
        worksheet = gc.open("拯救會員管理").sheet1
        return worksheet
    except Exception as e:
        st.error(f"無法開啟「拯救會員管理」表格。請確認服務帳號已獲得編輯權限。錯誤：{e}")
        return None

def get_raffle_sheet():
    """連接並取得抽獎名單的 Google Sheet 資料。"""
    try:
        worksheet = gc.open("抽獎名單").sheet1
        return worksheet
    except Exception as e:
        st.error(f"無法開啟「抽獎名單」表格。請確認服務帳號已獲得編輯權限。錯誤：{e}")
        return None

def draw_winners(df, num_winners):
    """從 DataFrame 中隨機選出指定數量的得獎者。"""
    if df.empty or num_winners <= 0:
        return None
    return random.sample(df.to_dict('records'), min(num_winners, len(df)))

def update_winners_status(sheet, winners):
    """將中獎者在 Google Sheet 中的狀態更新為 '是'。"""
    try:
        # 為了準確找到行數，讀取所有電子郵件
        emails_list = sheet.col_values(2)
        header_row = sheet.row_values(1)
        try:
            status_col = header_row.index('是否中獎') + 1
        except ValueError:
            st.error("Google Sheet 中找不到 '是否中獎' 欄位。請先手動新增此欄位。")
            return

        for winner in winners:
            try:
                # 找到電子郵件所在的行數 (1-based index)
                row_index = emails_list.index(winner['電子郵件']) + 1
                sheet.update_cell(row_index, status_col, "是")
            except ValueError:
                st.warning(f"找不到電子郵件為 '{winner['電子郵件']}' 的參與者，無法更新狀態。")
        
        st.success("🎉 中獎者的狀態已成功註記於 Google Sheet！")
    except Exception as e:
        st.error(f"更新 Google Sheet 時發生錯誤：{e}")

# 新增一個函式，用於根據 Sheet 標頭動態構建要新增的列
def build_append_row(sheet, nickname, points, account, password):
    """根據 Google Sheet 的實際標頭順序，創建要 append 的行資料列表。"""
    try:
        header = sheet.row_values(1)
    except Exception as e:
        st.error(f"無法取得 Google Sheet 標頭進行驗證: {e}")
        return None

    # 必須包含的欄位及其對應的值
    data_map = {
        '暱稱': str(nickname),
        '點數': int(points),
        # 確保帳號和密碼始終作為字串儲存
        '帳號': str(account),
        '密碼': str(password)
    }
    
    # 檢查所有必要欄位是否都存在於標頭中
    if not all(col in header for col in data_map.keys()):
        missing_cols = [col for col in data_map.keys() if col not in header]
        # 在側邊欄或主頁面顯示錯誤，取決於是哪個提交按鈕觸發
        error_location = st.sidebar if st.session_state.get('registration_trigger', False) else st
        error_location.error(f"錯誤：您的 '拯救會員管理' Sheet 缺少必要的欄位: {', '.join(missing_cols)}。")
        return None
    
    # 根據標頭順序構建要新增的列
    row_to_append = []
    for col_name in header:
        # 如果是我們關心的欄位，則放入值；否則放入空字串作為佔位符
        row_to_append.append(data_map.get(col_name, '')) 
        
    return row_to_append

# --- 主要應用程式邏輯 ---
def main():
    # 使用 session_state 來儲存登入狀態
    if 'admin_logged_in' not in st.session_state:
        st.session_state.admin_logged_in = False
    
    # 新增會員登入狀態
    if 'member_logged_in' not in st.session_state:
        st.session_state.member_logged_in = False
    if 'current_member_nickname' not in st.session_state:
        st.session_state.current_member_nickname = None
    if 'registration_trigger' not in st.session_state:
        st.session_state.registration_trigger = False # 用於追蹤註冊是從哪裡觸發的

    # 側邊欄 Logo
    logo_url = "https://raw.githubusercontent.com/ThomasPeng8888/streamlit-guppy/main/logo.png"
    # 圖片寬度設定為 150px
    st.sidebar.image(logo_url, caption="拯救會員管理系統", width=150)

    # ----------------------------------------------------
    # 📌 登入/註冊區塊 (保留在側邊欄)
    st.sidebar.markdown("---")
    
    sheet = get_points_sheet()
    if not sheet:
        return # 如果無法取得 Sheet，則停止應用程式

    if not st.session_state.member_logged_in:
        # ---------------------------
        # 1. 會員登入
        st.sidebar.subheader("會員登入")
        with st.sidebar.form(key="member_login_form"):
            member_account = st.text_input("帳號")
            member_password = st.text_input("密碼", type="password")
            login_member_button = st.form_submit_button("登入會員")
        
        if login_member_button:
            # 載入所有會員資料進行比對
            df = pd.DataFrame(sheet.get_all_records())
            
            required_cols = ['帳號', '密碼', '暱稱']
            if not all(col in df.columns for col in required_cols):
                st.sidebar.error("會員資料表格缺少 '帳號'、'密碼' 或 '暱稱' 欄位。請確認 Google Sheet 已更新。")
                return

            # 強制將 DataFrame 中的 '帳號' 和 '密碼' 轉換為字串型態
            df['帳號'] = df.get('帳號', pd.Series(dtype=str)).astype(str)
            df['密碼'] = df.get('密碼', pd.Series(dtype=str)).astype(str)
            
            # 尋找匹配的帳號和密碼
            match = df[(df['帳號'] == member_account) & (df['密碼'] == member_password)]
            
            if not match.empty:
                st.session_state.member_logged_in = True
                st.session_state.current_member_nickname = match.iloc[0]['暱稱']
                st.sidebar.success(f"登入成功！歡迎 {match.iloc[0]['暱稱']}")
                st.rerun()
            else:
                st.sidebar.error("帳號或密碼錯誤。")
        
        st.sidebar.markdown("---")
        
        # ---------------------------
        # 2. 新會員註冊 (公開註冊)
        st.sidebar.subheader("✨ 新會員註冊")
        with st.sidebar.form(key="public_registration_form"):
            new_nickname = st.text_input("輸入您的暱稱 (用於排行榜)")
            new_account = st.text_input("輸入您的帳號 (用於登入)")
            new_password = st.text_input("輸入您的密碼", type="password")
            register_button = st.form_submit_button("立即註冊")
        
        if register_button:
            st.session_state.registration_trigger = True # 標記註冊由側邊欄觸發
            if not new_nickname or not new_account or not new_password:
                st.sidebar.error("暱稱、帳號和密碼為必填欄位。")
            else:
                # 檢查暱稱和帳號是否重複
                all_values = sheet.get_all_values()
                
                if len(all_values) > 0:
                    header = all_values[0]
                    data_rows = all_values[1:]
                    
                    try:
                        # 找到 '暱稱' 和 '帳號' 欄位索引，用於重複性檢查
                        nickname_col_index = header.index('暱稱')
                        account_col_index = header.index('帳號')
                    except ValueError as e:
                        st.sidebar.error(f"會員資料表格缺少必要的欄位 ({e.args[0].split()[-1].strip()})。")
                        st.session_state.registration_trigger = False
                        return

                    # 取得現有資料進行比對
                    existing_nicknames = [row[nickname_col_index] for row in data_rows if len(row) > nickname_col_index]
                    existing_accounts = [row[account_col_index] for row in data_rows if len(row) > account_col_index]
                else:
                    existing_nicknames = []
                    existing_accounts = []

                if new_nickname in existing_nicknames:
                    st.sidebar.warning("此暱稱已被使用，請選擇其他暱稱。")
                elif new_account in existing_accounts:
                    st.sidebar.warning("此帳號已被使用，請選擇其他帳號。")
                else:
                    initial_points = 0
                    
                    # 使用動態構建的行資料，確保順序正確
                    row_to_append = build_append_row(sheet, new_nickname, initial_points, new_account, new_password)

                    if row_to_append:
                        # 執行 append_row
                        sheet.append_row(row_to_append)
                        
                        # 註冊成功後自動登入
                        st.session_state.member_logged_in = True
                        st.session_state.current_member_nickname = new_nickname
                        st.sidebar.success(f"會員 **{new_nickname}** 註冊成功並自動登入！")
                        st.balloons()
                        st.rerun()
            st.session_state.registration_trigger = False

    else:
        st.sidebar.success(f"已登入：**{st.session_state.current_member_nickname}**")
        if st.sidebar.button("登出會員"):
            st.session_state.member_logged_in = False
            st.session_state.current_member_nickname = None
            st.rerun()

    st.sidebar.markdown("---")
    # ----------------------------------------------------
    
    # 移除原本的 st.sidebar.title("導覽選單") 和 st.sidebar.radio
    
    # --- 頂部導覽列 (Main Content Tabs) ---
    st.title("應用程式功能區")
    
    tab_rank, tab_raffle, tab_admin = st.tabs(["會員點數排行榜", "抽獎活動", "管理員頁面"])


    # ----------------------------------------------------
    # 📌 頁面 1: 會員點數排行榜
    with tab_rank:
        st.subheader("會員點數排行榜 🏆")
        
        if not st.session_state.member_logged_in:
            st.warning("⚠️ 此頁面為會員專屬，請先登入帳號或註冊新會員。")
        else:
            st.info(f"歡迎 **{st.session_state.current_member_nickname}**！所有會員點數排名，會即時更新喔！")
            
            if st.button("重新整理排行榜"):
                st.rerun()

            if sheet:
                data = sheet.get_all_records()
                if data:
                    df = pd.DataFrame(data)
                    
                    # 確保 '點數' 欄位是數字類型，並處理錯誤
                    df['點數'] = pd.to_numeric(df.get('點數', pd.Series(dtype=int)), errors='coerce').fillna(0).astype(int)
                    
                    # 按點數降序排列，並重設索引
                    sorted_df = df.sort_values(by='點數', ascending=False).reset_index(drop=True)
                    
                    st.markdown("---")
                    st.subheader("點數冠軍榜 ✨")
                    
                    # 視覺化前三名
                    if len(sorted_df) >= 3:
                        top_3_cols = st.columns(3)
                        with top_3_cols[0]:
                            st.markdown(f"<h3 style='text-align: center;'>🥇 No.1</h3>", unsafe_allow_html=True)
                            # 使用 Markdown 確保暱稱不會過長而影響 metric 顯示
                            st.markdown(f"**{sorted_df.iloc[0]['暱稱']}**", unsafe_allow_html=True)
                            st.metric("點數", value=f"{sorted_df.iloc[0]['點數']:,}") # 點數加上千分位
                        with top_3_cols[1]:
                            st.markdown(f"<h3 style='text-align: center;'>🥈 No.2</h3>", unsafe_allow_html=True)
                            st.markdown(f"**{sorted_df.iloc[1]['暱稱']}**", unsafe_allow_html=True)
                            st.metric("點數", value=f"{sorted_df.iloc[1]['點數']:,}")
                        with top_3_cols[2]:
                            st.markdown(f"<h3 style='text-align: center;'>🥉 No.3</h3>", unsafe_allow_html=True)
                            st.markdown(f"**{sorted_df.iloc[2]['暱稱']}**", unsafe_allow_html=True)
                            st.metric("點數", value=f"{sorted_df.iloc[2]['點數']:,}")
                    elif len(sorted_df) > 0:
                        st.warning(f"會員人數不足3位 (目前 {len(sorted_df)} 位)，無法顯示完整前三名。")

                    st.markdown("---")
                    st.subheader("完整排行榜")
                    
                    # ----------------------------------------------------
                    # 🏆 UI/UX 優化：使用 Markdown/CSS 建立自定義且對齊的排行榜
                    # ----------------------------------------------------
                    st.markdown("""
                    <style>
                    /* Custom CSS for a better-aligned and styled leaderboard */
                    .leaderboard-header-row {
                        display: flex;
                        font-weight: bold;
                        font-size: 1.1em;
                        padding: 10px 15px;
                        background-color: #e6f3ff; /* 淺藍色背景 */
                        border-radius: 8px;
                        margin-bottom: 5px;
                        color: #1f78b4;
                    }

                    .leaderboard-item-row {
                        display: flex;
                        padding: 8px 15px;
                        margin-bottom: 5px;
                        border-radius: 8px;
                        align-items: center;
                        background-color: white;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
                        transition: all 0.2s ease-in-out;
                        /* 設置每個元素的高度，避免在 Streamlit 中因內容不同而導致的不對齊 */
                        min-height: 40px; 
                        color: #333333; /* ✨ 修改點：為所有行項目設定清晰的深灰色字體 */
                    }
                    .leaderboard-item-row:hover {
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                        transform: translateY(-1px);
                    }

                    /* 使用固定百分比寬度確保對齊 */
                    .leaderboard-rank { width: 15%; text-align: left; font-weight: bold; }
                    .leaderboard-name { width: 60%; text-align: left; }
                    .leaderboard-points { width: 25%; text-align: right; font-weight: bold; color: #0056b3; } /* ✨ 修改點：改為清晰的深藍色 */

                    /* 特殊前三名樣式 */
                    .rank-1 { background-color: #fffde7; border-left: 5px solid #FFD700; }
                    .rank-2 { background-color: #f7f7f7; border-left: 5px solid #C0C0C0; }
                    .rank-3 { background-color: #fff0e6; border-left: 5px solid #CD7F32; }

                    .leaderboard-name, .leaderboard-points, .leaderboard-rank {
                        /* 確保文字不會換行，使用省略號 */
                        white-space: nowrap; 
                        overflow: hidden; 
                        text-overflow: ellipsis;
                        align-self: center; /* 垂直居中 */
                    }
                    </style>
                    """, unsafe_allow_html=True)

                    # 排行榜標頭
                    st.markdown("""
                    <div class='leaderboard-header-row'>
                        <span class='leaderboard-rank'>排名</span>
                        <span class='leaderboard-name'>暱稱</span>
                        <span class='leaderboard-points'>點數</span>
                    </div>
                    """, unsafe_allow_html=True)


                    for index, row in sorted_df.iterrows():
                        rank = index + 1
                        nickname = row['暱稱']
                        points = f"{row['點數']:,}" # 點數加上千分位格式

                        # 根據排名決定樣式
                        if rank == 1:
                            rank_icon = "🥇 No.1"
                            row_class = "rank-1"
                        elif rank == 2:
                            rank_icon = "🥈 No.2"
                            row_class = "rank-2"
                        elif rank == 3:
                            rank_icon = "🥉 No.3"
                            row_class = "rank-3"
                        else:
                            rank_icon = f"No.{rank}"
                            row_class = ""

                        # 渲染每一行排行榜
                        st.markdown(f"""
                        <div class='leaderboard-item-row {row_class}'>
                            <span class='leaderboard-rank'>{rank_icon}</span>
                            <span class='leaderboard-name'>{nickname}</span>
                            <span class='leaderboard-points'>{points}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    # ----------------------------------------------------
                    
                else:
                    st.warning("目前沒有任何會員資料可顯示。")
    
    # ----------------------------------------------------
    # 📌 頁面 2: 抽獎活動
    with tab_raffle:
        st.subheader("抽獎活動報名表單")
        
        if not st.session_state.member_logged_in:
            st.warning("⚠️ 此頁面為會員專屬，請先登入帳號或註冊新會員才能參與抽獎活動。")
        else:
            st.info("請填寫您的資訊，以便參與抽獎！")

            with st.form(key="registration_form"):
                name = st.text_input("姓名")
                email = st.text_input("電子郵件")
                submit_button = st.form_submit_button("提交報名")
            
            if submit_button:
                if not name or not email:
                    st.error("姓名和電子郵件為必填欄位。")
                else:
                    raffle_sheet = get_raffle_sheet()
                    if raffle_sheet:
                        # 檢查電子郵件重複性 (從第 2 行開始檢查，忽略標題)
                        try:
                            # 假設電子郵件在第 2 欄
                            emails_list = raffle_sheet.col_values(2)[1:] 
                        except Exception as e:
                            st.error(f"無法讀取電子郵件列表：{e}")
                            return
                        
                        if email in emails_list:
                            st.warning("您使用的電子郵件已報名過，請勿重複提交。")
                        else:
                            # 假設抽獎名單表格結構是 [姓名, 電子郵件, 是否中獎 (此欄位應該是手動新增的)]
                            # 為了確保資料順序正確，需要讀取標頭並動態建立行
                            try:
                                raffle_header = raffle_sheet.row_values(1)
                                row_to_append = []
                                data_map = {'姓名': name, '電子郵件': email, '是否中獎': ''}
                                for col_name in raffle_header:
                                    row_to_append.append(data_map.get(col_name, ''))

                                raffle_sheet.append_row(row_to_append)
                                st.success("報名成功！感謝您的參與！")
                                st.balloons()
                            except Exception as e:
                                st.error(f"新增抽獎報名資料時發生錯誤：{e}")


    # ----------------------------------------------------
    # 📌 頁面 3: 管理員頁面
    with tab_admin:
        if not st.session_state.admin_logged_in:
            with st.form(key="admin_login_form"):
                st.subheader("管理員登入 🔐")
                password = st.text_input("輸入密碼", type="password")
                login_button = st.form_submit_button("登入")

            if login_button:
                if password and password == st.secrets.get("admin_password"):
                    st.session_state.admin_logged_in = True
                    st.success("登入成功！")
                    st.rerun()
                else:
                    st.error("密碼錯誤。")
        else:
            st.title("管理員控制台 ⚙️")
            st.markdown("---")
            
            # 管理員頁面內部的子選單仍使用 st.tabs
            tab1, tab2, tab3 = st.tabs(["點數管理", "抽獎管理", "新增會員"])

            # 點數管理功能
            with tab1:
                st.subheader("會員點數管理")
                if st.button("重新整理會員列表", key="refresh_points_admin"):
                    st.rerun()

                if sheet:
                    data = sheet.get_all_records()
                    if data:
                        df = pd.DataFrame(data)
                        
                        # 確保 '點數' 欄位是數字類型
                        df['點數'] = pd.to_numeric(df.get('點數', pd.Series(dtype=int)), errors='coerce').fillna(0).astype(int)
                        
                        # 確保暱稱也是字串，用於下拉選單和後續查找
                        df['暱稱'] = df.get('暱稱', pd.Series(dtype=str)).astype(str)
                        
                        st.markdown("#### 所有會員列表")
                        
                        # 只顯示 '暱稱' 和 '點數' 欄位
                        display_cols = ['暱稱', '點數']
                        available_cols = [col for col in display_cols if col in df.columns]
                        st.dataframe(df[available_cols], hide_index=True)
                        
                        if '暱稱' in df.columns:
                            member_nickname = st.selectbox(
                                "選擇要管理的會員暱稱：",
                                options=df['暱稱'].tolist()
                            )
                        else:
                            st.warning("會員資料表格缺少 '暱稱' 欄位。")
                            member_nickname = None

                        if member_nickname:
                            member_data = df[df['暱稱'] == member_nickname].iloc[0]
                            st.markdown("---")
                            st.metric(label="目前點數", value=member_data['點數'])
                            
                            with st.form(key="points_form"):
                                points_change = st.number_input(
                                    "輸入要增減的點數：",
                                    value=0,
                                    step=1
                                )
                                submit_points = st.form_submit_button("更新點數")
                            
                            if submit_points:
                                header_row = sheet.row_values(1)
                                try:
                                    points_col_index = header_row.index('點數') + 1
                                except ValueError:
                                    st.error("點數表格中找不到 '點數' 欄位。")
                                    return

                                current_points = member_data['點數']
                                new_points = int(current_points) + points_change
                                
                                if new_points < 0:
                                    st.warning("點數不能為負數，請重新輸入。")
                                else:
                                    try:
                                        # 找出暱稱所在行 (gspread 索引從 1 開始)
                                        nicknames_list = sheet.col_values(1)
                                        row_index = nicknames_list.index(member_nickname) + 1 
                                        
                                        # 更新點數：row_index 是行數 (1-based)
                                        sheet.update_cell(row_index, points_col_index, new_points)
                                        st.success(f"已將會員 **{member_nickname}** 的點數更新為 **{new_points}**！")
                                        st.rerun() # 重新運行以更新顯示的點數
                                    except Exception as e:
                                        st.error(f"更新點數時發生錯誤：{e}")
                    else:
                        st.warning("目前沒有任何會員。")
            
            # 抽獎管理功能
            with tab2:
                st.subheader("抽獎控制台")
                if st.button("重新整理抽獎名單", key="refresh_raffle_admin"):
                    st.rerun()

                raffle_sheet = get_raffle_sheet()
                if raffle_sheet:
                    data = raffle_sheet.get_all_records()
                    if data:
                        df = pd.DataFrame(data)
                        
                        if '是否中獎' not in df.columns:
                            st.error("抽獎名單表格中找不到 '是否中獎' 欄位，請在 Google Sheet 中手動新增。")
                            eligible_df = pd.DataFrame() 
                        else:
                            # 強制將 '是否中獎' 欄位轉換為字串，以避免因資料型態不一致導致過濾失敗
                            df['是否中獎'] = df.get('是否中獎', pd.Series(dtype=str)).astype(str)
                            # 過濾掉已經中獎的參與者
                            eligible_df = df[df['是否中獎'] != '是'] 

                        st.markdown(f"### 目前共有 {len(eligible_df)} 位合格參與者：")
                        st.dataframe(eligible_df, hide_index=True)

                        if not eligible_df.empty:
                            num_winners = st.number_input(
                                "請輸入要抽出的得獎者人數：", 
                                min_value=1, 
                                max_value=len(eligible_df), 
                                value=min(1, len(eligible_df)),
                                step=1
                            )
                            if st.button("開始抽獎！"):
                                if num_winners > 0 and num_winners <= len(eligible_df):
                                    with st.spinner("正在抽出幸運兒..."):
                                        time.sleep(2)
                                        winners = draw_winners(eligible_df, num_winners)
                                        
                                        if winners:
                                            st.balloons()
                                            st.success("🎉🎉🎉 恭喜以下幸運兒！ 🎉🎉🎉")
                                            for winner in winners:
                                                st.success(f"**姓名**：{winner['姓名']}")
                                                st.write(f"**聯絡信箱**：{winner['電子郵件']}")
                                            update_winners_status(raffle_sheet, winners)
                                            st.rerun()
                                        else:
                                            st.error("抽獎失敗，請確認名單。")
                                else:
                                    st.error("抽獎人數必須大於 0 且不超過合格參與者總數。")
                        else:
                            st.warning("目前沒有任何合格的參與者，所有人都已經中過獎。")
                    else:
                        st.warning("目前沒有任何參與者報名。")
            
            # 新增會員功能（管理員手動新增）
            with tab3:
                st.subheader("新增會員 (管理員專用) ➕")
                with st.form(key="registration_form_new"):
                    nickname = st.text_input("暱稱")
                    account = st.text_input("帳號 (用於登入)")
                    password = st.text_input("密碼 (用於登入)", type="password")
                    initial_points = 0
                    submit_button = st.form_submit_button("創建會員")

                if submit_button:
                    if not nickname or not account or not password:
                        st.error("暱稱、帳號和密碼為必填欄位。")
                    else:
                        # 檢查暱稱和帳號是否重複
                        all_values = sheet.get_all_values()
                        
                        if len(all_values) > 0:
                            header = all_values[0]
                            data_rows = all_values[1:]
                            
                            try:
                                nickname_col_index = header.index('暱稱')
                                account_col_index = header.index('帳號')
                            except ValueError as e:
                                st.error(f"會員資料表格缺少必要的欄位 ({e.args[0].split()[-1].strip()})。")
                                return
                            
                            existing_nicknames = [row[nickname_col_index] for row in data_rows if len(row) > nickname_col_index]
                            existing_accounts = [row[account_col_index] for row in data_rows if len(row) > account_col_index]
                        else:
                            existing_nicknames = []
                            existing_accounts = []

                        if nickname in existing_nicknames:
                            st.warning("此暱稱已被使用，請選擇其他暱稱。")
                        elif account in existing_accounts:
                            st.warning("此帳號已被使用，請選擇其他帳號。")
                        else:
                            # 使用動態構建的行資料，確保順序正確
                            row_to_append = build_append_row(sheet, nickname, initial_points, account, password)

                            if row_to_append:
                                # 執行 append_row
                                sheet.append_row(row_to_append)
                                st.success(f"會員 **{nickname}** 創建成功！帳號：{account}。")
                                st.balloons()


if __name__ == "__main__":
    main()