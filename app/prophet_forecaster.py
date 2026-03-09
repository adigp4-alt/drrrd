import logging
import pandas as pd
from prophet import Prophet
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def generate_prophet_forecast(history_records, days_ahead=30):
    """
    Takes standard historical OHLCV data and uses Meta's Prophet model
    to generate a non-linear trajectory forecast.
    
    Returns a dictionary structured for Chart.js plotting:
    {
        "dates": ["YYYY-MM-DD", ...],
        "historical_prices": [float, ...],
        "forecast_dates": ["YYYY-MM-DD", ...],
        "yhat": [float, ...],       # The predicted price
        "yhat_lower": [float, ...], # Lower confidence bound
        "yhat_upper": [float, ...]  # Upper confidence bound
    }
    """
    if not history_records or len(history_records) < 30:
        return None
        
    try:
        # Prophet strictly requires columns named 'ds' (datestamp) and 'y' (value)
        df = pd.DataFrame(history_records)
        prophet_df = pd.DataFrame({
            'ds': pd.to_datetime(df['date']),
            'y': df['close']
        })
        
        # HISTORICAL ACCURACY (MAPE)
        # To show confidence, we run a mini-backtest on the last 30 days
        mape = None
        if len(prophet_df) > 60:
            # Train on everything except last 30 days
            train_df = prophet_df.iloc[:-30]
            test_df = prophet_df.iloc[-30:]
            
            test_model = Prophet(daily_seasonality=False, weekly_seasonality=True, yearly_seasonality=True)
            # Suppress Prophet logs for the test model
            logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
            test_model.fit(train_df)
            
            # Predict the 30 days we held out
            future_test = test_model.make_future_dataframe(periods=30, freq='B')
            # Prophet might generate more than 30 rows if there are weekends, so we inner join with test_df on 'ds'
            forecast_test = test_model.predict(future_test)
            merged = pd.merge(test_df, forecast_test[['ds', 'yhat']], on='ds')
            
            if len(merged) > 0:
                # Mean Absolute Percentage Error
                error_pcts = abs((merged['y'] - merged['yhat']) / merged['y'])
                mape = error_pcts.mean()
        
        # Now train the MAIN model on ALL data for the actual future forecast
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=True,
            interval_width=0.80 # 80% confidence interval for standard stock charting
        )
        
        model.fit(prophet_df)
        
        # Create a future dataframe extending 'days_ahead' business days into the future
        future = model.make_future_dataframe(periods=days_ahead, freq='B')
        forecast = model.predict(future)
        
        # We need to construct the payload for the frontend charting library
        # 1. Provide the historical actuals
        # 2. Provide the newly generated future trajectory
        
        historical_dates = prophet_df['ds'].dt.strftime('%Y-%m-%d').tolist()
        historical_prices = prophet_df['y'].tolist()
        
        # Only take the rows where 'ds' is strictly greater than the last historical date
        last_hist_date = prophet_df['ds'].max()
        future_forecast = forecast[forecast['ds'] > last_hist_date]
        
        mape_display = f"{(1 - mape) * 100:.1f}%" if mape is not None else "N/A"
        
        mape_display = f"{max(0, (1 - mape)) * 100:.1f}%" if mape is not None else "N/A"
        
        payload = {
            "dates": historical_dates,
            "historical_prices": historical_prices,
            "forecast_dates": future_forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
            "yhat": [round(val, 2) for val in future_forecast['yhat'].tolist()],
            "yhat_lower": [round(val, 2) for val in future_forecast['yhat_lower'].tolist()],
            "yhat_upper": [round(val, 2) for val in future_forecast['yhat_upper'].tolist()],
            "accuracy_score": mape_display
        }
        
        return payload
        
    except Exception as e:
        logger.error(f"Prophet Generator Error: {e}")
        return None
