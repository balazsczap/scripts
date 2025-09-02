# /// script
# dependencies = [
#     "pandas>=2.0.0",
#     "plotly>=5.17.0",
# ]
# ///

#####
# run via `uv run .\summary.py transactions_export.csv`
# first transaction in Aug 2014, export from ..July
#####

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import sys
from pathlib import Path
import webbrowser

# needed since header row of raw export had unnecessary nbsps and whitespaces, leading to wrong column parsing
def fix_header_line(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    header_line = lines[0]
    
    # Replace any non-tab whitespace with nothing, but preserve tabs
    fixed_header = ''.join(char if char == '\t' or not char.isspace() else '' 
                          for char in header_line)
    lines[0] = fixed_header
    
    # Write back to a temporary file or overwrite
    temp_file = file_path + '_fixed.csv'
    with open(temp_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    return temp_file

def read_and_process_csv(csv_file_path):
    """Read CSV and process bank transactions - keep only required columns"""
    try:
        fixed_file = fix_header_line(csv_file_path)

        df = pd.read_csv(fixed_file, sep='\t', encoding='utf-8', skipinitialspace=True)
        
        # Remove any completely empty rows
        df = df.dropna(how='all')

        print(df.columns)
        print(df[df.columns[0]])
        
        # Check for non-HUF currencies first, just for safety
        non_huf = df[df['összegdevizaneme'] != 'HUF']
        if not non_huf.empty:
            print(f"Error: Found {len(non_huf)} transactions with non-HUF currency:")
            for _, row in non_huf.iterrows():
                print(f"  Date: {row['könyvelésdátuma']}, Amount: {row['összeg']} {row['összegdevizaneme']}")
            return None
        
        df['date'] = pd.to_datetime(df['könyvelésdátuma'], format='%Y.%m.%d')

        df = df[df['típus'] != 'Számlamegszüntetés átvezetéssel'] # old account was weirdly merged

        df = df.sort_values('date')
        
        df['date'] = pd.to_datetime(df['date'])

        # Group by date and add incremental hours (export only has date, needed for better detail in chart)
        df['date'] = df.groupby(df['date'].dt.date)['date'].transform(
            lambda x: x + pd.to_timedelta(range(len(x)), unit='H')
        )

        df['balance'] = df['összeg'].cumsum()
        df['description'] = df['partnerelnevezése'].fillna(
            df['közlemény'].fillna('No Description')
        )
        return df
        
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

def create_plotly_chart(df):
    """Create interactive Plotly chart"""
    
    hover_data = []
    for _, row in df.iterrows():        
        amount_color = "🟢" if row['összeg'] > 0 else "🔴" if row['összeg'] < 0 else "⚪"
        amount_sign = "+" if row['összeg'] > 0 else ""
        
        hover_text = (
            f"<b>{row['date'].strftime('%Y-%m-%d')}</b><br>"
            f"<b>Balance:</b> {row['balance']:,.0f} HUF<br>"
            f"<b>Change:</b> {amount_color} {amount_sign}{row['összeg']:,.0f} HUF<br>"
            f"<b>Description:</b> {row['description']}"
            
        )
        hover_data.append(hover_text)
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['balance'],
        mode='lines+markers',
        name='Balance',
        line=dict(
            color='rgba(55, 128, 191, 1)',
            width=3,
            shape='spline'
        ),
        marker=dict(
            size=6,
            color='rgba(55, 128, 191, 1)',
            line=dict(width=2, color='white')
        ),
        fill='tozeroy',
        fillcolor='rgba(55, 128, 191, 0.1)',
        hovertemplate='%{customdata}<extra></extra>',
        customdata=hover_data
    ))
    
    fig.add_hline(
        y=0, 
        line_dash="dash", 
        line_color="rgba(150, 150, 150, 0.8)",
        annotation_text="Zero Balance",
        annotation_position="bottom right"
    )
    
    positive_mask = df['balance'] >= 0
    if positive_mask.any():
        fig.add_trace(go.Scatter(
            x=df[positive_mask]['date'],
            y=df[positive_mask]['balance'],
            mode='none',
            fill='tozeroy',
            fillcolor='rgba(72, 187, 120, 0.2)',
            name='Positive Balance',
            showlegend=False,
            hoverinfo='skip'
        ))
    
    negative_mask = df['balance'] < 0
    if negative_mask.any():
        fig.add_trace(go.Scatter(
            x=df[negative_mask]['date'],
            y=df[negative_mask]['balance'],
            mode='none',
            fill='tozeroy',
            fillcolor='rgba(245, 101, 101, 0.2)',
            name='Negative Balance',
            showlegend=False,
            hoverinfo='skip'
        ))
    
    current_balance = df['balance'].iloc[-1]
    min_balance = df['balance'].min()
    max_balance = df['balance'].max()
    
    fig.update_layout(
        title=dict(
            text=f"💰 Bank Account Balance - Current: {current_balance:,.0f} HUF",
            font=dict(size=24, color='#2D3748'),
            x=0.5,
            xanchor='center'
        ),
        xaxis=dict(
            title="Date",
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.2)',
            showspikes=True,
            spikecolor="rgba(128, 128, 128, 0.5)",
            spikethickness=1
        ),
        yaxis=dict(
            title="Balance (HUF)",
            showgrid=True,
            gridcolor='rgba(128, 128, 128, 0.2)',
            tickformat=',.0f',
            showspikes=True,
            spikecolor="rgba(128, 128, 128, 0.5)",
            spikethickness=1
        ),
        hovermode='x unified',
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family="Open Sans, sans-serif", size=12, color='#2D3748'),
        margin=dict(l=80, r=80, t=80, b=80),
        height=600,
        showlegend=False
    )
    
    fig.update_layout(
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=7, label="7d", step="day", stepmode="backward"),
                    dict(count=30, label="30d", step="day", stepmode="backward"),
                    dict(count=90, label="3m", step="day", stepmode="backward"),
                    dict(count=180, label="6m", step="day", stepmode="backward"),
                    dict(step="all", label="All")
                ]),
                bgcolor="rgba(55, 128, 191, 0.1)",
                bordercolor="rgba(55, 128, 191, 0.3)",
                borderwidth=1
            ),
            rangeslider=dict(visible=True, bgcolor="rgba(55, 128, 191, 0.05)"),
            type="date"
        )
    )
    
    fig.add_annotation(
        x=df[df['balance'] == max_balance]['date'].iloc[0],
        y=max_balance,
        text=f"Peak: {max_balance:,.0f} HUF",
        showarrow=True,
        arrowhead=2,
        arrowcolor="green",
        bgcolor="rgba(72, 187, 120, 0.8)",
        bordercolor="green",
        font=dict(color="white")
    )
    
    if min_balance < 0:
        fig.add_annotation(
            x=df[df['balance'] == min_balance]['date'].iloc[0],
            y=min_balance,
            text=f"Lowest: {min_balance:,.0f} HUF",
            showarrow=True,
            arrowhead=2,
            arrowcolor="red",
            bgcolor="rgba(245, 101, 101, 0.8)",
            bordercolor="red",
            font=dict(color="white")
        )
    
    return fig

def main():
    if len(sys.argv) != 2:
        print("Usage: python bank_chart.py <csv_file_path>")
        sys.exit(1)
    
    csv_file_path = sys.argv[1]
    
    df = read_and_process_csv(csv_file_path)
    if df is None:
        sys.exit(1)
    
    print(f"✅ Successfully processed {len(df)} transactions")
    print(f"📅 Date range: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")
    print(f"💰 Final balance: {df['balance'].iloc[-1]:,.0f} HUF")
    print(f"📊 Balance range: {df['balance'].min():,.0f} to {df['balance'].max():,.0f} HUF")
    
    fig = create_plotly_chart(df)
    
    output_file = Path("bank_balance_chart.html")
    fig.write_html(
        str(output_file),
        config={
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'bank_balance_chart',
                'height': 600,
                'width': 1200,
                'scale': 2
            }
        },
        include_plotlyjs='cdn'
    )
    
    print(f"📊 Interactive chart saved as: {output_file.absolute()}")
    
    try:
        webbrowser.open(f"file://{output_file.absolute()}")
        print("🌐 Opening chart in your default browser...")
    except Exception as e:
        print(f"Could not open browser automatically: {e}")
        print(f"Please open {output_file.absolute()} manually in your browser")

if __name__ == "__main__":
    main()