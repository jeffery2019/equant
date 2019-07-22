import talib
import numpy as np

p1=5
p2=20


def initialize(context): 
    SetActual()
    SetBarInterval("NYMEX|F|CL|1909", 'T', 30, 2000)
    pass

def handle_data(context):
    print("333333333 ", context.triggerType())
    # 使用talib计算均价
    ma1 = talib.MA(Close(), timeperiod=p1, matype=0)
    ma2 = talib.MA(Close(), timeperiod=p2, matype=0)
    
    # 绘制指标图形
    PlotNumeric("ma1", ma1[-1], color=RGB_Red())
    PlotNumeric("ma2", ma2[-1], color=RGB_Green())    
    PlotNumeric("fit", NetProfit(), RGB_Red(), False)

    # 执行下单操作
    #if MarketPosition() <= 0 and ma1[-1] > ma2[-1]:
    if context.triggerType() == "K":
        Buy(1, Close()[-1])
    #if MarketPosition() >= 0 and ma1[-1] < ma2[-1]:
        #SellShort(1, Close()[-1])
