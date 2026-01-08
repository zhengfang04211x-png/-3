import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
import io
from datetime import datetime
import platform

# 设置页面配置
st.set_page_config(
    page_title="企业套保运营分析系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 配置matplotlib中文字体
plt.style.use('seaborn-v0_8-whitegrid')
system_name = platform.system()
if system_name == "Windows":
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial']
elif system_name == "Darwin":
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC']
else:
    plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False

# ==============================================================================
# 核心计算函数
# ==============================================================================

def load_and_filter_data(df, start_date, end_date):
    """加载和过滤数据"""
    df.columns = [str(c).strip() for c in df.columns]
    cols = df.columns
    col_time = next((c for c in cols if '时间' in c or 'Date' in c or 'date' in c.lower()), None)
    col_spot = next((c for c in cols if '现货' in c), None)
    col_fut = next((c for c in cols if ('期货' in c or '主力' in c) and '价格' in c), None)

    if col_time and col_spot and col_fut:
        df = df.rename(columns={col_time: 'Date', col_spot: 'Spot', col_fut: 'Futures'})
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        for col in ['Spot', 'Futures']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
        df = df.dropna(subset=['Date', 'Spot', 'Futures'])
        df = df.sort_values('Date').reset_index(drop=True)

        if start_date:
            df = df[df['Date'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['Date'] <= pd.to_datetime(end_date)]
        return df.reset_index(drop=True) if len(df) > 0 else None
    return None


def calculate_metrics(df, cfg):
    """计算指标"""
    q = cfg['quantity']
    ratio = cfg['hedge_ratio']
    m_rate = cfg['margin_rate']
    days = cfg['holding_days']

    inject_r = cfg['fund_inject_ratio']
    withdraw_r = cfg['fund_withdraw_ratio']

    # 基础计算
    df['Basis'] = df['Spot'] - df['Futures']

    # 周期性风险
    df['Cycle_PnL_NoHedge'] = df['Spot'].diff(days) * q
    df['Cycle_Futures_PnL'] = -(df['Futures'].diff(days)) * q * ratio
    df['Cycle_PnL_Hedge'] = df['Cycle_PnL_NoHedge'] + df['Cycle_Futures_PnL']

    # 动态资金流模拟
    equity_list = []
    margin_req_list = []
    cash_in_list = []
    cash_out_list = []
    risk_degree_list = []

    current_price = df['Futures'].iloc[0]
    initial_equity = current_price * q * ratio * m_rate * inject_r
    current_equity = initial_equity

    for i in range(len(df)):
        price = df['Futures'].iloc[i]

        if i > 0:
            prev_price = df['Futures'].iloc[i - 1]
            daily_pnl = -(price - prev_price) * q * ratio
            current_equity += daily_pnl

        req_margin = price * q * ratio * m_rate
        margin_req_list.append(req_margin)

        threshold_lower = req_margin * inject_r
        threshold_upper = req_margin * withdraw_r

        daily_in = 0
        daily_out = 0

        if current_equity < threshold_lower:
            injection = threshold_lower - current_equity
            current_equity += injection
            daily_in = injection
        elif current_equity > threshold_upper:
            surplus = current_equity - threshold_upper
            current_equity -= surplus
            daily_out = surplus

        cash_in_list.append(daily_in)
        cash_out_list.append(daily_out)
        equity_list.append(current_equity)

        curr_risk = (current_equity / req_margin) if req_margin > 0 else 0
        risk_degree_list.append(curr_risk)

    df['Account_Equity'] = equity_list
    df['Margin_Required'] = margin_req_list
    df['Cash_Injection'] = cash_in_list
    df['Cash_Withdrawal'] = cash_out_list
    df['Risk_Degree'] = risk_degree_list

    df['Line_Inject'] = df['Margin_Required'] * inject_r
    df['Line_Withdraw'] = df['Margin_Required'] * withdraw_r

    # 账面价值对冲效果
    cum_withdrawal = pd.Series(cash_out_list).cumsum()
    cum_injection = pd.Series(cash_in_list).cumsum()
    net_cash_flow = cum_withdrawal - cum_injection

    base_asset = (df['Spot'].iloc[0] * q) + initial_equity
    current_total_asset = (df['Spot'] * q) + df['Account_Equity'] + net_cash_flow

    df['Value_Change_NoHedge'] = (df['Spot'] - df['Spot'].iloc[0]) * q
    df['Value_Change_Hedged'] = current_total_asset - base_asset

    return df


def create_excel_report(df, cfg):
    """创建Excel报表"""
    inject_r = cfg['fund_inject_ratio']
    withdraw_r = cfg['fund_withdraw_ratio']

    cols_export = [
        'Date', 'Spot', 'Futures', 'Basis',
        'Margin_Required', 'Account_Equity', 'Risk_Degree',
        'Line_Inject', 'Line_Withdraw',
        'Cash_Injection', 'Cash_Withdrawal',
        'Value_Change_Hedged'
    ]

    export_df = df[cols_export].copy()

    wan_cols = ['Margin_Required', 'Account_Equity', 'Line_Inject', 'Line_Withdraw',
                'Cash_Injection', 'Cash_Withdrawal', 'Value_Change_Hedged']
    for c in wan_cols:
        export_df[c] = export_df[c] / 10000

    export_df['Risk_Degree'] = export_df['Risk_Degree'].apply(lambda x: f"{x * 100:.1f}%")

    export_df.columns = [
        '日期', '现货单价', '期货单价', '基差',
        '占用保证金(万元)', '账户权益(万元)', '风险度(%)',
        f'补金线_{inject_r}x(万元)', f'提金线_{withdraw_r}x(万元)',
        '当日需补金(万元)', '当日可出金(万元)',
        '套保后净值变动(万元)'
    ]

    def get_status(row):
        if row['当日需补金(万元)'] > 0:
            return '🔴 补金'
        if row['当日可出金(万元)'] > 0:
            return '🟢 提金'
        return '⚪ 正常'

    export_df.insert(0, '状态', export_df.apply(get_status, axis=1))
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        export_df.to_excel(writer, index=False, sheet_name='套保运营报表')
    output.seek(0)
    return output


# ==============================================================================
# Streamlit UI
# ==============================================================================

st.title("📊 企业套保运营分析系统")
st.markdown("---")

# 侧边栏 - 参数配置
with st.sidebar:
    st.header("⚙️ 参数配置")
    
    st.subheader("📁 数据上传")
    uploaded_file = st.file_uploader("上传CSV文件", type=['csv'], help="请上传包含日期、现货价格、期货价格的CSV文件")
    
    st.subheader("⏳ 时间范围")
    start_date = st.date_input("开始日期", value=datetime(2023, 1, 1))
    end_date = st.date_input("结束日期", value=datetime(2025, 12, 20))
    
    st.subheader("🏭 业务参数")
    quantity = st.number_input("库存量 (吨)", min_value=1.0, value=30.0, step=1.0)
    hedge_ratio = st.slider("套保比例", min_value=0.0, max_value=2.0, value=1.0, step=0.1)
    margin_rate = st.slider("保证金率", min_value=0.05, max_value=0.30, value=0.12, step=0.01)
    
    st.subheader("💰 资金管理")
    fund_inject_ratio = st.slider("补金线倍数", min_value=1.0, max_value=2.0, value=1.2, step=0.1)
    fund_withdraw_ratio = st.slider("提金线倍数", min_value=1.0, max_value=3.0, value=1.5, step=0.1)
    
    st.subheader("⚠️ 风险参数")
    holding_days = st.number_input("持仓天数", min_value=1, value=30, step=1)

# 主内容区
if uploaded_file is not None:
    try:
        # 读取文件
        encoding = 'gbk'
        try:
            df = pd.read_csv(uploaded_file, encoding=encoding)
        except:
            encoding = 'utf-8-sig'
            df = pd.read_csv(uploaded_file, encoding=encoding)
        
        st.success(f"✅ 文件读取成功！编码: {encoding}")
        
        # 显示数据预览
        with st.expander("📋 数据预览", expanded=False):
            st.dataframe(df.head(10))
            st.info(f"数据总行数: {len(df)}")
        
        # 处理数据
        processed_df = load_and_filter_data(df, start_date, end_date)
        
        if processed_df is None or len(processed_df) == 0:
            st.error("❌ 数据处理失败！请检查CSV文件是否包含：日期列、现货价格列、期货价格列")
        else:
            st.success(f"✅ 数据处理成功！有效数据行数: {len(processed_df)}")
            
            # 配置参数
            config = {
                'quantity': quantity,
                'hedge_ratio': hedge_ratio,
                'margin_rate': margin_rate,
                'fund_inject_ratio': fund_inject_ratio,
                'fund_withdraw_ratio': fund_withdraw_ratio,
                'holding_days': holding_days,
                'dpi': 100  # Web显示用较低DPI
            }
            
            # 计算指标
            with st.spinner("🔄 正在计算指标..."):
                result_df = calculate_metrics(processed_df.copy(), config)
            
            st.success("✅ 计算完成！")
            
            # 生成报表和图表
            st.markdown("---")
            st.header("📈 分析结果")
            
            # 计算套保稳定性指标
            val_raw = result_df['Value_Change_NoHedge'] / 10000
            val_hedge = result_df['Value_Change_Hedged'] / 10000
            
            # 1. 现货波动风险(标准差)
            spot_volatility_risk = val_raw.std()
            
            # 2. 套保后剩余波动
            hedged_remaining_volatility = val_hedge.std()
            volatility_reduction_pct = (1 - hedged_remaining_volatility / spot_volatility_risk) * 100 if spot_volatility_risk > 0 else 0
            
            # 3. 累计调仓净额（累计提金 - 累计补金）
            total_withdraw = result_df['Cash_Withdrawal'].sum() / 10000
            total_inject = result_df['Cash_Injection'].sum() / 10000
            cumulative_adjustment_net = total_withdraw - total_inject
            
            # 4. 最大亏损修复额（未套保的最小值 - 套保后的最小值，表示套保避免的最大亏损）
            min_loss_raw = val_raw.min()  # 未套保的最大亏损
            min_loss_hedge = val_hedge.min()  # 套保后的最大亏损
            max_loss_recovery = min_loss_raw - min_loss_hedge  # 修复的金额（正值为避免了亏损）
            
            # 关键指标卡片 - 按图片要求显示
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(
                    "现货波动风险(标准差)",
                    f"{spot_volatility_risk:.2f}万",
                    help="未套保情况下现货价格波动带来的风险（标准差）"
                )
            with col2:
                st.metric(
                    "套保后剩余波动",
                    f"{hedged_remaining_volatility:.2f}万",
                    delta=f"降低{volatility_reduction_pct:.1f}%",
                    help="套保后的剩余波动风险，显示相比未套保降低的百分比"
                )
            with col3:
                st.metric(
                    "累计调仓净额",
                    f"{cumulative_adjustment_net:.2f}万",
                    delta="正值为净提金" if cumulative_adjustment_net > 0 else "负值为净补金",
                    help="累计调仓净额 = 累计提金 - 累计补金"
                )
            with col4:
                st.metric(
                    "最大亏损修复额",
                    f"{max_loss_recovery:.2f}万",
                    delta=f"未套保亏损 {min_loss_raw:.2f}万 → 套保后 {min_loss_hedge:.2f}万",
                    help="套保避免的最大亏损金额，正数表示通过套保减少了亏损"
                )
            
            # 额外显示资金管理指标
            with st.expander("💰 资金管理详情", expanded=False):
                col5, col6, col7, col8 = st.columns(4)
                with col5:
                    total_inject = result_df['Cash_Injection'].sum() / 10000
                    st.metric("累计补金", f"{total_inject:.2f}万元")
                with col6:
                    total_withdraw = result_df['Cash_Withdrawal'].sum() / 10000
                    st.metric("累计提金", f"{total_withdraw:.2f}万元")
                with col7:
                    net_cash_flow = (total_withdraw - total_inject)
                    st.metric("净资金流", f"{net_cash_flow:.2f}万元", 
                             delta="正值为净提金" if net_cash_flow > 0 else "负值为净补金")
                with col8:
                    inject_count = (result_df['Cash_Injection'] > 0).sum()
                    withdraw_count = (result_df['Cash_Withdrawal'] > 0).sum()
                    st.metric("操作频次", f"补金{inject_count}次 | 提金{withdraw_count}次")
            
            # 图1: 价格与基差
            st.subheader("📊 图1: 期现价格走势与基差监控")
            fig1, ax1 = plt.subplots(figsize=(12, 6))
            ax1.set_title('期现价格走势与基差监控', fontsize=14, fontweight='bold')
            
            l1, = ax1.plot(result_df['Date'], result_df['Spot'] / 10000, 'b-', label='现货价格 (左轴)')
            l2, = ax1.plot(result_df['Date'], result_df['Futures'] / 10000, color='orange', linestyle='--', label='期货价格 (左轴)')
            ax1.set_ylabel('单价 (万元/吨)')
            ax1.grid(True, alpha=0.3)
            
            ax1_r = ax1.twinx()
            basis_wan = result_df['Basis'] / 10000
            ax1_r.fill_between(result_df['Date'], basis_wan, 0, color='gray', alpha=0.2, label='基差范围 (右轴)')
            l3, = ax1_r.plot(result_df['Date'], basis_wan, color='gray', linewidth=1, alpha=0.5, label='基差走势 (右轴)')
            ax1_r.set_ylabel('基差 (万元/吨)', color='gray')
            
            lines = [l1, l2, l3]
            labels = [l.get_label() for l in lines]
            ax1.legend(lines, labels, loc='upper left')
            
            corr = result_df['Spot'].corr(result_df['Futures'])
            ax1.text(0.5, -0.15, f"【分析结论】: 期现相关性 {corr:.2f}。灰色区域为基差(现货-期货)，基差波动直接影响套保效率。",
                    transform=ax1.transAxes, ha='center', va='top', fontsize=10,
                    bbox=dict(facecolor='#f0f0f0', edgecolor='none', pad=5))
            
            plt.tight_layout()
            st.pyplot(fig1)
            plt.close(fig1)
            
            # 图2: 波动分布
            st.subheader("📊 图2: 资产波动分布对比")
            fig2, ax2 = plt.subplots(figsize=(12, 6))
            sns.kdeplot(result_df['Cycle_PnL_NoHedge'].dropna() / 10000, fill=True, color='red', alpha=0.3, label='未套保波动', ax=ax2)
            sns.kdeplot(result_df['Cycle_PnL_Hedge'].dropna() / 10000, fill=True, color='green', alpha=0.6, label='套保后波动', ax=ax2)
            ax2.set_title(f'资产波动分布对比 (持货{config["holding_days"]}天)', fontsize=14, fontweight='bold')
            ax2.set_xlabel('盈亏变动 (万元)')
            ax2.legend()
            plt.tight_layout()
            st.pyplot(fig2)
            plt.close(fig2)
            
            # 图3: 资金通道
            st.subheader("📊 图3: 资金安全通道监控")
            fig3, ax3 = plt.subplots(figsize=(12, 6))
            ax3.set_title(f'资金安全通道监控 ({fund_inject_ratio}x ~ {fund_withdraw_ratio}x)', 
                         fontsize=14, fontweight='bold', color='darkblue')
            
            l_inject = result_df['Line_Inject'] / 10000
            l_withdraw = result_df['Line_Withdraw'] / 10000
            l_equity = result_df['Account_Equity'] / 10000
            l_margin = result_df['Margin_Required'] / 10000
            
            ax3.fill_between(result_df['Date'], l_inject, l_withdraw, color='gray', alpha=0.1, label='安全操作区')
            ax3.plot(result_df['Date'], l_equity, color='green', linewidth=2, label='账户权益')
            ax3.plot(result_df['Date'], l_inject, color='red', linestyle='--', linewidth=1, label='补金线')
            ax3.plot(result_df['Date'], l_withdraw, color='blue', linestyle='--', linewidth=1, label='提金线')
            ax3.plot(result_df['Date'], l_margin, color='black', linewidth=1, alpha=0.5, label='最低保证金')
            
            inject_days = result_df[result_df['Cash_Injection'] > 0]
            withdraw_days = result_df[result_df['Cash_Withdrawal'] > 0]
            if len(inject_days) > 0:
                ax3.scatter(inject_days['Date'], inject_days['Account_Equity'] / 10000, 
                          color='red', marker='^', s=40, zorder=5, label='补金点')
            if len(withdraw_days) > 0:
                ax3.scatter(withdraw_days['Date'], withdraw_days['Account_Equity'] / 10000, 
                          color='blue', marker='v', s=40, zorder=5, label='提金点')
            
            ax3.set_ylabel('资金金额 (万元)')
            ax3.legend(loc='upper left')
            ax3.text(0.5, -0.15, f"【分析结论】: 权益控制在 {fund_inject_ratio}~{fund_withdraw_ratio} 倍保证金区间。红点补金，蓝点提金。",
                    transform=ax3.transAxes, ha='center', va='top', fontsize=10,
                    bbox=dict(facecolor='#f0f0f0', edgecolor='none', pad=5))
            plt.tight_layout()
            st.pyplot(fig3)
            plt.close(fig3)
            
            # 图4: 对冲效果
            st.subheader("📊 图4: 账面资产价值变动对比")
            fig4, ax4 = plt.subplots(figsize=(12, 6))
            ax4.set_title('账面资产价值变动对比', fontsize=14, fontweight='bold')
            
            val_raw = result_df['Value_Change_NoHedge'] / 10000
            val_hedge = result_df['Value_Change_Hedged'] / 10000
            
            ax4.plot(result_df['Date'], val_raw, color='red', alpha=0.4, linewidth=1.5, label='未套保：库存价值波动')
            ax4.plot(result_df['Date'], val_hedge, color='green', linewidth=2.5, label='套保后：总资产平稳')
            ax4.axhline(0, color='black', linestyle=':', alpha=0.5)
            ax4.set_ylabel('资产价值变动 (万元)')
            ax4.legend(loc='upper left')
            
            std_raw = val_raw.std()
            std_hedge = val_hedge.std()
            reduce_pct = (1 - std_hedge / std_raw) * 100 if std_raw != 0 else 0
            ax4.text(0.5, -0.15, f"【分析结论】: 通过对冲，资产价值波动率降低了 {reduce_pct:.1f}%。",
                    transform=ax4.transAxes, ha='center', va='top', fontsize=10,
                    bbox=dict(facecolor='#f0f0f0', edgecolor='none', pad=5))
            plt.tight_layout()
            st.pyplot(fig4)
            plt.close(fig4)
            
            # 下载Excel报表
            st.markdown("---")
            st.subheader("📥 下载报表")
            excel_buffer = create_excel_report(result_df, config)
            st.download_button(
                label="📊 下载Excel运营报表",
                data=excel_buffer,
                file_name=f"资金安全与对冲日报_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"❌ 发生错误: {str(e)}")
        st.exception(e)
        
else:
    st.info("👈 请在左侧上传CSV文件开始分析")
    st.markdown("""
    ### 📝 使用说明
    
    1. **上传CSV文件**: 文件需包含以下列：
       - 日期列（列名包含"时间"或"Date"）
       - 现货价格列（列名包含"现货"）
       - 期货价格列（列名包含"期货"或"主力"，且包含"价格"）
    
    2. **配置参数**: 在左侧边栏调整各项业务参数
    
    3. **查看结果**: 系统会自动生成4个分析图表和详细报表
    
    4. **下载报表**: 点击下载按钮获取Excel格式的运营报表
    
    ### 💡 提示
    - CSV文件编码支持GBK和UTF-8
    - 所有金额单位自动转换为万元显示
    - 图表可直接查看或下载
    """)
