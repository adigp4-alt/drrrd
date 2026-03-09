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
        
        # Initialize the model with yearly and weekly seasonality
        # We disable daily seasonality since we only have daily close data
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
        
        payload = {
            "dates": historical_dates,
            "historical_prices": historical_prices,
            "forecast_dates": future_forecast['ds'].dt.strftime('%Y-%m-%d').tolist(),
            "yhat": [round(val, 2) for val in future_forecast['yhat'].tolist()],
            "yhat_lower": [round(val, 2) for val in future_forecast['yhat_lower'].tolist()],
            "yhat_upper": [round(val, 2) for val in future_forecast['yhat_upper'].tolist()]
        }
        
        return payload
        
    except Exception as e:
        logger.error(f"Prophet Generator Error: {e}")
        return None
