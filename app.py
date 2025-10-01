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
    """連接並取得會員點數管理的 Google Sheet 資料。"""
    try:
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

def is_email_already_registered(sheet, email):
    """檢查電子郵件是否已存在於 Google Sheet 中。"""
    try:
        emails_list = sheet.col_values(2)
        return email in emails_list
    except Exception as e:
        st.error(f"檢查重複電子郵件時發生錯誤：{e}")
        return False

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
                row_index = emails_list.index(winner['電子郵件']) + 1
                sheet.update_cell(row_index, status_col, "是")
            except ValueError:
                st.warning(f"找不到電子郵件為 '{winner['電子郵件']}' 的參與者，無法更新狀態。")
        
        st.success("🎉 中獎者的狀態已成功註記於 Google Sheet！")
    except Exception as e:
        st.error(f"更新 Google Sheet 時發生錯誤：{e}")

# --- 主要應用程式邏輯 ---
def main():
    # 使用 session_state 來儲存登入狀態
    if 'admin_logged_in' not in st.session_state:
        st.session_state.admin_logged_in = False
    
    st.sidebar.title("導覽選單")
    mode = st.sidebar.radio("請選擇頁面", ["會員點數排行榜", "抽獎活動", "管理員頁面"])

    # 顯示會員點數排行榜
    if mode == "會員點數排行榜":
        st.title("會員點數排行榜 🏆")
        st.info("所有會員點數排名，會即時更新喔！")
        
        # 新增重新整理按鈕
        if st.button("重新整理"):
            st.rerun()

        sheet = get_points_sheet()
        if sheet:
            data = sheet.get_all_records()
            if data:
                df = pd.DataFrame(data)
                
                # 確保 '點數' 欄位是數字類型，以便正確排序
                df['點數'] = pd.to_numeric(df['點數'])
                
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
                    st.warning("會員人數不足3位，無法顯示完整前三名。")
                
                st.markdown("---")
                st.subheader("完整排行榜")
                
                # 新增一個 '排名' 欄位，從 1 開始編號，並加上 'No.' 前綴
                sorted_df.insert(0, '排名', ['No.' + str(i) for i in range(1, 1 + len(sorted_df))])
                
                # 顯示排名表，並隱藏預設索引
                st.dataframe(sorted_df, hide_index=True)
            else:
                st.warning("目前沒有任何會員資料可顯示。")
    
    # 顯示抽獎活動報名頁面
    elif mode == "抽獎活動":
        st.title("抽獎活動報名表單")
        st.info("請填寫您的資訊，以便參與抽獎！")

        with st.form(key="registration_form"):
            name = st.text_input("姓名")
            email = st.text_input("電子郵件")
            submit_button = st.form_submit_button("提交報名")
        
        if submit_button:
            if not name or not email:
                st.error("姓名和電子郵件為必填欄位。")
            else:
                sheet = get_raffle_sheet()
                if sheet:
                    if is_email_already_registered(sheet, email):
                        st.warning("您使用的電子郵件已報名過，請勿重複提交。")
                    else:
                        sheet.append_row([name, email])
                        st.success("報名成功！感謝您的參與！")
                        st.balloons()
    
    # 顯示管理員頁面（統一登入）
    elif mode == "管理員頁面":
        if not st.session_state.admin_logged_in:
            with st.form(key="admin_login_form"):
                st.subheader("管理員登入 🔐")
                password = st.text_input("輸入密碼", type="password")
                login_button = st.form_submit_button("登入")

            if login_button:
                if password == st.secrets.get("admin_password"):
                    st.session_state.admin_logged_in = True
                    st.success("登入成功！")
                    st.rerun()
                else:
                    st.error("密碼錯誤。")
        else:
            st.title("管理員控制台 ⚙️")
            st.markdown("---")
            # 將 tab1, tab2 改為 tab1, tab2, tab3
            tab1, tab2, tab3 = st.tabs(["點數管理", "抽獎管理", "新增會員"])

            # 點數管理功能
            with tab1:
                st.subheader("會員點數管理")
                if st.button("重新整理會員列表", key="refresh_points_admin"):
                    st.rerun()

                sheet = get_points_sheet()
                if sheet:
                    data = sheet.get_all_records()
                    if data:
                        df = pd.DataFrame(data)
                        st.markdown("#### 所有會員列表")
                        st.dataframe(df)
                        
                        member_nickname = st.selectbox(
                            "選擇要管理的會員暱稱：",
                            options=df['暱稱'].tolist()
                        )
                        
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
                                new_points = int(member_data['點數']) + points_change
                                if new_points < 0:
                                    st.warning("點數不能為負數，請重新輸入。")
                                else:
                                    try:
                                        row_index = df.index[df['暱稱'] == member_nickname].tolist()[0] + 2
                                        sheet.update_cell(row_index, 2, new_points)
                                        st.success(f"已將會員 **{member_nickname}** 的點數更新為 **{new_points}**！")
                                    except Exception as e:
                                        st.error(f"更新點數時發生錯誤：{e}")
                    else:
                        st.warning("目前沒有任何會員。")
            
            # 抽獎管理功能
            with tab2:
                st.subheader("抽獎控制台")
                if st.button("重新整理抽獎名單", key="refresh_raffle_admin"):
                    st.rerun()

                sheet = get_raffle_sheet()
                if sheet:
                    data = sheet.get_all_records()
                    if data:
                        df = pd.DataFrame(data)
                        eligible_df = df[df['是否中獎'] != '是']
                        
                        st.markdown(f"### 目前共有 {len(eligible_df)} 位合格參與者：")
                        st.dataframe(eligible_df)

                        if not eligible_df.empty:
                            num_winners = st.number_input(
                                "請輸入要抽出的得獎者人數：", 
                                min_value=1, 
                                max_value=len(eligible_df), 
                                value=1, 
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
                                            st.success("🎉🎉🎉")
                                            update_winners_status(sheet, winners)
                                        else:
                                            st.error("抽獎失敗，請確認名單。")
                                else:
                                    st.error("抽獎人數必須大於 0 且不超過合格參與者總數。")
                        else:
                            st.warning("目前沒有任何合格的參與者，所有人都已經中過獎。")
                    else:
                        st.warning("目前沒有任何參與者報名。")
            
            # 新增會員功能（新獨立的標籤）
            with tab3:
                st.subheader("新增會員 ➕")
                with st.form(key="registration_form_new"):
                    nickname = st.text_input("暱稱")
                    initial_points = 0
                    submit_button = st.form_submit_button("創建會員")

                if submit_button:
                    if not nickname:
                        st.error("暱稱為必填欄位。")
                    else:
                        sheet = get_points_sheet()
                        if sheet:
                            existing_nicknames = sheet.col_values(1)
                            if nickname in existing_nicknames:
                                st.warning("此暱稱已被使用，請選擇其他暱稱。")
                            else:
                                sheet.append_row([nickname, initial_points])
                                st.success(f"會員 **{nickname}** 創建成功！初始點數為 {initial_points}。")
                                st.balloons()


if __name__ == "__main__":
    main()
