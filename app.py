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
                # 由於 get_all_records() 會將數字讀成數字，這裡使用 col_values(2) 確保讀取的是字串列表
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
        st.sidebar.error(f"錯誤：您的 '拯救會員管理' Sheet 缺少必要的欄位: {', '.join(missing_cols)}。")
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

    # 側邊欄 Logo
    logo_url = "https://raw.githubusercontent.com/ThomasPeng8888/streamlit-guppy/main/logo.png"
    # 圖片寬度設定為 150px
    st.sidebar.image(logo_url, caption="拯救會員管理系統", width=150)

    # ----------------------------------------------------
    # 📌 登入/註冊區塊
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

            # 【修正點 1】強制將 DataFrame 中的 '帳號' 和 '密碼' 轉換為字串型態
            # 這能確保與 st.text_input 傳入的字串進行正確比對，解決純數字帳密登入失敗的問題。
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
            if not new_nickname or not new_account or not new_password:
                st.sidebar.error("暱稱、帳號和密碼為必填欄位。")
            else:
                # 檢查暱稱和帳號是否重複
                # get_all_values() 預設讀取為字串，所以這裡不需要額外的型態轉換
                all_values = sheet.get_all_values()
                
                # 確保至少有標題列
                if len(all_values) > 0:
                    header = all_values[0]
                    data_rows = all_values[1:]
                    
                    try:
                        # 找到 '暱稱' 和 '帳號' 欄位索引，用於重複性檢查
                        nickname_col_index = header.index('暱稱')
                        account_col_index = header.index('帳號')
                    except ValueError as e:
                        st.sidebar.error(f"會員資料表格缺少必要的欄位 ({e.args[0].split()[-1].strip()})。")
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

    else:
        st.sidebar.success(f"已登入：**{st.session_state.current_member_nickname}**")
        if st.sidebar.button("登出會員"):
            st.session_state.member_logged_in = False
            st.session_state.current_member_nickname = None
            st.rerun()

    st.sidebar.markdown("---")
    # ----------------------------------------------------
    
    st.sidebar.title("導覽選單")
    mode = st.sidebar.radio("請選擇頁面", ["會員點數排行榜", "抽獎活動", "管理員頁面"])

    # 顯示會員點數排行榜 (需登入)
    if mode == "會員點數排行榜":
        st.title("會員點數排行榜 🏆")
        
        if not st.session_state.member_logged_in:
            st.warning("⚠️ 此頁面為會員專屬，請先登入帳號或註冊新會員。")
            return

        st.info(f"歡迎 **{st.session_state.current_member_nickname}**！所有會員點數排名，會即時更新喔！")
        
        if st.button("重新整理"):
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
                        st.markdown(f"**🥇 No.1**")
                        st.metric(sorted_df.iloc[0]['暱稱'], value=sorted_df.iloc[0]['點數'])
                    with top_3_cols[1]:
                        st.markdown(f"**🥈 No.2**")
                        st.metric(sorted_df.iloc[1]['暱稱'], value=sorted_df.iloc[1]['點數'])
                    with top_3_cols[2]:
                        st.markdown(f"**🥉 No.3**")
                        st.metric(sorted_df.iloc[2]['暱稱'], value=sorted_df.iloc[2]['點數'])
                elif len(sorted_df) > 0:
                    st.warning(f"會員人數不足3位 (目前 {len(sorted_df)} 位)，無法顯示完整前三名。")

                st.markdown("---")
                st.subheader("完整排行榜")
                
                # 新增一個 '排名' 欄位，從 1 開始編號，並加上 'No.' 前綴
                # 只顯示與排名相關的欄位
                display_df = sorted_df[['暱稱', '點數']].copy()
                display_df.insert(0, '排名', ['No.' + str(i) for i in range(1, 1 + len(display_df))])

                st.dataframe(display_df, hide_index=True)
            else:
                st.warning("目前沒有任何會員資料可顯示。")
    
    # 顯示抽獎活動報名頁面 (需登入)
    elif mode == "抽獎活動":
        st.title("抽獎活動報名表單")
        
        if not st.session_state.member_logged_in:
            st.warning("⚠️ 此頁面為會員專屬，請先登入帳號或註冊新會員才能參與抽獎活動。")
            return
            
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
                        emails_list = raffle_sheet.col_values(2)[1:] 
                    except Exception as e:
                        st.error(f"無法讀取電子郵件列表：{e}")
                        return
                    
                    if email in emails_list:
                        st.warning("您使用的電子郵件已報名過，請勿重複提交。")
                    else:
                        # 假設抽獎名單表格結構是 [姓名, 電子郵件]
                        raffle_sheet.append_row([name, email])
                        st.success("報名成功！感謝您的參與！")
                        st.balloons()
    
    # 顯示管理員頁面
    elif mode == "管理員頁面":
        if not st.session_state.admin_logged_in:
            with st.form(key="admin_login_form"):
                st.subheader("管理員登入 🔐")
                password = st.text_input("輸入密碼", type="password")
                login_button = st.form_submit_button("登入")

            if login_button:
                # 【修正點 2】確保管理員密碼也使用 .get() 檢查，避免 secrets 中沒有該 key 時出錯
                if password and password == st.secrets.get("admin_password"):
                    st.session_state.admin_logged_in = True
                    st.success("登入成功！")
                    st.rerun()
                else:
                    st.error("密碼錯誤。")
        else:
            st.title("管理員控制台 ⚙️")
            st.markdown("---")
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
                        
                        # 【修正點 3】確保暱稱也是字串，用於下拉選單和後續查找
                        df['暱稱'] = df.get('暱稱', pd.Series(dtype=str)).astype(str)
                        
                        st.markdown("#### 所有會員列表")
                        # --- 根據用戶要求修改：只顯示 '暱稱' 和 '點數' 欄位 ---
                        display_cols = ['暱稱', '點數']
                        available_cols = [col for col in display_cols if col in df.columns]
                        st.dataframe(df[available_cols], hide_index=True)
                        # ----------------------------------------------------
                        
                        member_nickname = st.selectbox(
                            "選擇要管理的會員暱稱：",
                            options=df['暱稱'].tolist()
                        )
                        
                        if member_nickname:
                            # 由於上面已將暱稱轉換為 str，這裡的查詢會更可靠
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
                                        # 這裡使用 col_values(1) 讀取的也是字串，與 member_nickname 匹配
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
