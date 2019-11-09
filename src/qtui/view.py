import datetime
import json
import os
import pandas as pd
import shutil
import sys
import traceback
from threading import Thread
import time

import qdarkstyle
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QPoint, QUrl, pyqtSignal, pyqtSlot, QSharedMemory, QThread, QTimer, QDir
from PyQt5.QtGui import QTextCursor, QIcon
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings
from PyQt5.QtWidgets import *

from engine.strategy_cfg_model_new import StrategyConfig_new
from report.fieldConfigure import RunMode, StrategyStatus
from qtui.contractSelect import Ui_contractSelect
from qtui.contractWin import Ui_contractWin
from qtui.strategyPolicy import Ui_strategyMainWin

from api.base_api import BaseApi
from api.api_func import _all_func_
from capi.com_types import *
from qtui.utils import parseStrategtParam, Tree, get_strategy_filters

strategy_path = os.path.join(os.getcwd(), 'strategy')


class StrategyPolicy(QMainWindow, Ui_strategyMainWin):
    def __init__(self, control, path, flag=False, master=None, param=None, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.contractTableWidget.hideColumn(4)
        self.contractTableWidget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.contractTableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cycleLineEdit.setValidator(QtGui.QIntValidator())  # 设置只能输入数字
        self.initFundlineEdit.setValidator(QtGui.QIntValidator())  # 设置只能输入数字
        self.defaultOrderLineEdit.setValidator(QtGui.QIntValidator())  # 设置只能输入数字
        self.miniOrderLineEdit.setValidator(QtGui.QIntValidator(1, 1000))  # 设置只能输入数字
        self.marginRateLineEdit.setValidator(QtGui.QIntValidator(1, 100))  # 设置只能输入数字
        self.openFeeRateLineEdit.setValidator(QtGui.QIntValidator(1, 100))  # 设置只能输入数字
        self.closeFeeRateLineEdit.setValidator(QtGui.QIntValidator(1, 100))  # 设置只能输入数字
        self.slippageLineEdit.setValidator(QtGui.QIntValidator())  # 设置只能输入数字
        self.isConOpenTimesLineEdit.setValidator(QtGui.QIntValidator(1, 100))  # 设置只能输入数字
        self.openTimeslineEdit.setValidator(QtGui.QIntValidator(1, 100))  # 设置只能输入数字
        self.addTimerButton.clicked.connect(self.add_timer)
        self.deleteTimerButton.clicked.connect(self.delete_timer)
        self.addContract.clicked.connect(self.create_contract_win)
        self.deleteContract.clicked.connect(self.delete_contract)
        self.updateContract.clicked.connect(self.update_contract)
        self.cancel.clicked.connect(self.close)
        self.confirm.clicked.connect(self.enter)

        self._control = control

        # 用户设置信息
        self.config = {}

        # 获取用户参数
        self._userParam = param if param else {}
        # 策略路径
        self._strategyPath = path
        # 是否时属性设置运行窗口标志位
        self._paramFlag = flag

        self._strConfig = StrategyConfig_new()

        # 设置属性值
        self.setDefaultConfigure()
        self.contractWin = ContractWin()

    def add_timer(self):
        t = self.timerEdit.text()
        ti = t.replace(':', '')
        self.timerListWidget.addItem(ti)

    def delete_timer(self):
        row = self.timerListWidget.currentRow()
        if row != -1:
            self.timerListWidget.removeItemWidget(self.timerListWidget.takeItem(row))

    def create_contract_win(self):
        # 增加合约槽函数，弹出合约设置窗口
        self.contractWin.confirm_signal.connect(self.add_contract)
        self.contractWin.setWindowModality(Qt.ApplicationModal)  # 阻塞父窗口
        self.contractWin.show()

    def contractSelect(self, exchange, commodity, contract):
        self.contractSelectWin = ContractSelect(exchange, commodity, contract)
        self.contractSelectWin.setWindowModality(Qt.ApplicationModal)  # 阻塞父窗口
        self.contractSelectWin.show()
        self.contractSelectWin.confirm.clicked.connect(self.set_contract)

    def set_contract(self):
        if self.contractSelectWin.choice_tree.topLevelItemCount() == 1:
            self.contractWin.contractCodeLineEdit.setText(self.contractSelectWin.choice_tree.topLevelItem(0).text(0))
            self.contractSelectWin.close()

    def add_contract(self, sample_dict):
        if self.contractWin.row != -1:
            row = self.contractWin.row
        else:
            row = self.contractTableWidget.rowCount()
            self.contractTableWidget.setRowCount(row + 1)
        KLineType = sample_dict.get('KLineType')
        if KLineType == 'T':
            _KlineType = '分笔'
        elif KLineType == 'M':
            _KlineType = '分钟'
        elif KLineType == 'D':
            _KlineType = '日线'
        else:  # KLineType == 'S'
            _KlineType = '秒'
        if sample_dict.get('AllK'):
            start = '所有K线'
        elif sample_dict.get('BeginTime'):
            start = sample_dict.get('BeginTime')
        elif sample_dict.get('KLineCount'):
            start = sample_dict.get('KLineCount')
        else:
            start = '不执行历史K线'

        items = [sample_dict.get('contract'), _KlineType, sample_dict.get('KLineSlice'), start, json.dumps(sample_dict)]
        for j in range(len(items)):
            item = QTableWidgetItem(str(items[j]))
            self.contractTableWidget.setItem(row, j, item)

    def delete_contract(self):
        items = self.contractTableWidget.selectedItems()
        if items:
            self.contractTableWidget.removeRow(items[0].row())

    def update_contract(self):
        items = self.contractTableWidget.selectedItems()
        if not items:
            return
        row = items[0].row()
        item = self.contractTableWidget.item(row, 4)
        sample_dict = json.loads(item.text())
        self.contractWin.confirm_signal.connect(self.add_contract)
        # ------------------设置合约-----------------------------
        self.contractWin.contractCodeLineEdit.setText(sample_dict.get('contract'))
        self.contractWin.contractCodeLineEdit.setEnabled(False)
        self.contractWin.select.setEnabled(False)
        # ------------------设置k线类型--------------------------
        k_type = ['T', 'S', 'M', 'D']
        t = sample_dict.get('KLineType')
        self.contractWin.kLineTypeComboBox.setCurrentIndex(k_type.index(t))
        # ------------------设置k线周期--------------------------
        if not t == 'T':  # k线类型不是分笔的时候设置k线周期
            k_period = [1, 2, 3, 5, 10, 15, 30, 60, 120]
            self.contractWin.kLinePeriodComboBox.setCurrentIndex(k_period.index(int(sample_dict.get('KLineSlice'))))
        else:  # k线类型为分笔的时候，k线周期设置不可用
            self.contractWin.kLinePeriodComboBox.setEnabled(False)
        # ------------------设置运算起始点-----------------------
        if sample_dict.get('AllK'):
            self.contractWin.AllkLineRadioButton.setChecked(True)
        elif sample_dict.get('BeginTime'):
            self.contractWin.startDateRadioButton.setChecked(True)
            self.contractWin.startDateLineEdit.setText(sample_dict.get('BeginTime'))
        elif sample_dict.get('UseSample'):  # TODO 确认条件True还是False时候执行
            self.contractWin.historyRadioButton.setChecked(True)
        elif sample_dict.get('KLineCount'):
            self.contractWin.qtyRadioButton.setChecked(True)
            self.contractWin.qtylineEdit.setText(str(sample_dict.get('KLineCount')))
        else:
            pass
        self.contractWin.row = row
        self.contractWin.setWindowModality(Qt.ApplicationModal)  # 阻塞父窗口
        self.contractWin.show()

    def enter(self):
        # TODO: IntVar()显示时会补充一个0？？？
        user = self.userComboBox.currentText()  # 用户
        initFund = self.initFundlineEdit.text()  # 初始资金
        defaultType = self.defaultOrderComboBox.currentText()  # 默认下单方式
        defaultQty = self.defaultOrderLineEdit.text()  # 默认下单量
        minQty = self.miniOrderLineEdit.text()  # 最小下单量
        # hedge = self.hedge.get()
        margin = self.marginRateLineEdit.text()  # 保证金率

        openType = self.openTypeComboBox.currentText()  # 开仓收费方式
        closeType = self.closeTypeComboBox.currentText()  # 开仓收费方式
        openFee = self.openFeeRateLineEdit.text()  # 开仓手续费（率）
        closeFee = self.closeFeeRateLineEdit.text()  # 平仓手续费（率）

        tradeDirection = self.tradeDirectionComboBox.currentText()  # 交易方向
        slippage = self.slippageLineEdit.text()  # 滑点损耗
        # TODO: contract另外保存了一个变量，不再分解了
        # contractInfo = self.contract.get()

        # contract = (contractInfo.rstrip("\n")).split("\n")

        # if len(contract) == 0:
        #     messagebox.showinfo("提示", "未选择合约")
        #     return
        # else:
        #     contractInfo = (contract.rstrip(", ")).split(", ")

        timer = ''  # 时间
        count = self.timerListWidget.count()
        for i in range(count):
            text = self.timerListWidget.item(i).text() + '\n' if i != count - 1 else self.timerListWidget.item(i).text()
            timer += text

        isCycle = int(self.cycleCheckBox.isChecked())  # 是否按周期触发
        cycle = self.cycleLineEdit.text()  # 周期
        isKLine = int(self.KLineCheckBox.isChecked())  # K线触发
        isSnapShot = int(self.snapShotCheckBox.isChecked())  # 行情触发
        isTrade = int(self.tradeCheckBox.isChecked())  # 交易数据触发

        # beginDate = self.beginDate.get()
        # # beginDateFormatter = parseYMD(beginDate)
        # fixQty = self.fixQty.get()
        # sampleVar = self.sampleVar.get()

        sendOrderMode = 0 if self.sendOrderRealtime.isChecked() else 1  # 发单时机： 0. 实时发单 1. K线稳定后发单

        isActual = int(self.actualCheckBox.isChecked())  # 实时发单
        isAlarm = int(self.alarmCheckBox.isChecked())  # 发单报警
        isPop = int(self.allowCheckBox.isChecked())  # 允许弹窗
        # isContinue = self.isContinue.get()
        isOpenTimes = int(self.openTimesCheckBox.isChecked())  # 每根K线同向开仓次数标志
        openTimes = self.openTimeslineEdit.text()  # 每根K线同向开仓次数

        isConOpenTimes = int(self.isConOpenTimesCheckBox.isChecked())  # 最大连续同向开仓次数标志

        conOpenTimes = self.isConOpenTimesLineEdit.text()  # 最大连续同向开仓次数
        canClose = int(self.canCloseCheckBox.isChecked())  # 开仓的当前K线不允许平仓
        canOpen = int(self.canOpenCheckBox.isChecked())  # 平仓的当前K线不允许开仓

        # -------------转换定时触发的时间形式--------------------------
        time = timer.split("\n")
        timerFormatter = []
        for t in time:
            if t:
                timerFormatter.append(t)

        if float(initFund) < 1000:
            QMessageBox.warning(self, "极星量化", "初始资金不能小于1000元", QMessageBox.Yes)
            return

        if cycle == "":
            QMessageBox.warning(self, "极星量化", "定时触发周期不能为空", QMessageBox.Yes)
            return
        elif int(cycle) % 100 != 0:
            QMessageBox.warning(self, "极星量化", "定时触发周期为100的整数倍", QMessageBox.Yes)
            return
        else:
            pass

        if minQty == "":
            QMessageBox.warning(self, "极星量化", "最小下单量不能为空", QMessageBox.Yes)
            return
        elif int(minQty) > MAXSINGLETRADESIZE:
            QMessageBox.warning(self, "极星量化", "最小下单量不能大于1000", QMessageBox.Yes)
            return
        else:
            pass

        if isConOpenTimes:
            if conOpenTimes == '' or int(conOpenTimes) < 1 or int(conOpenTimes) > 100:
                QMessageBox.warning(self, "极星量化", "最大连续同向开仓次数必须介于1-100之间", QMessageBox.Yes)
                return

        if isOpenTimes:
            if openTimes == '' or int(openTimes) < 1 or int(openTimes) > 100:
                QMessageBox.warning(self, "极星量化", "每根K线同向开仓次数必须介于1-100之间", QMessageBox.Yes)
                return

        # 用户是否确定用新参数重新运行
        if self._paramFlag:
            reply = QMessageBox.question(self, '提示', '点确定后会重新运行策略？', QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return

        # TODO: 合约设置，K线类型， K线周期、运算起始点设置
        # 多合约信息：
        contsInfo = []
        for i in range(self.contractTableWidget.rowCount()):
            contValues = []
            for j in range(self.contractTableWidget.columnCount()):
                contValues.append(self.contractTableWidget.item(i, j).text())
            contsInfo.append(contValues)

            # kLineTypeDict = {
            #     "分时": 't',
            #     "分笔": 'T',
            #     "秒线": 'S',
            #     "分钟": 'M',
            #     "小时": 'H',
            #     "日线": 'D',
            #     "周线": 'W',
            #     "月线": 'm',
            #     "年线": 'Y'
            # }

            kLineTypeDict = {
                "分笔": 'T',
                "秒": 'T',
                "分钟": 'M',
                "日线": 'D',
            }

            contCode = contValues[0]
            kTypeValue = kLineTypeDict[contValues[1]]
            kSliceValue = int(contValues[2])

            samValue = ''
            if contValues[3] == "所有K线":
                samValue = 'A'
            elif contValues[3] == "不执行历史K线":
                samValue = 'N'
            elif json.loads(contValues[4]).get('BeginTime'):
                samValue = json.loads(contValues[4]).get('BeginTime')
            elif json.loads(contValues[4]).get('KLineCount'):
                samValue = json.loads(contValues[4]).get('KLineCount')

            self._strConfig.setBarInfoInSample(contCode, kTypeValue, kSliceValue, samValue)

        # K线触发
        if isKLine:
            self._strConfig.setTrigger(5)
        # 即时行情触发
        if isSnapShot:
            self._strConfig.setTrigger(1)
        # 交易数据触发
        if isTrade:
            self._strConfig.setTrigger(2)
        # 周期触发
        if isCycle:
            self._strConfig.setTrigger(3, int(cycle))
        # 指定时刻
        if timer:
            self._strConfig.setTrigger(4, timerFormatter)

        # 发单设置
        if sendOrderMode == 0:
            self._strConfig.setOrderWay('1')
        else:
            self._strConfig.setOrderWay('2')

        # 连续运行
        # self.config["RunMode"]["Simulate"]["Continues"] = True
        # 运行模式
        if isActual:
            self._strConfig.setActual()
        # 发单报警
        self._strConfig.setAlarm(True) if int(isAlarm) else self._strConfig.setAlarm(False)
        # 允许弹窗
        self._strConfig.setPop(True) if int(isPop) else self._strConfig.setPop(False)

        # 账户
        self._strConfig.setUserNo(user)
        # 初始资金
        self._strConfig.setInitCapital(int(initFund))
        # 交易方向
        if tradeDirection == "双向交易":
            self._strConfig.setTradeDirection(0)
        elif tradeDirection == "仅多头":
            self._strConfig.setTradeDirection(1)
        else:
            self._strConfig.setTradeDirection(2)

        # 默认下单量
        if defaultType == "按固定合约数":
            self._strConfig.setOrderQty("1", int(defaultQty))
        elif defaultType == "按固定资金":
            self._strConfig.setOrderQty("2", float(defaultQty))
        elif defaultType == "按资金比例":
            self._strConfig.setOrderQty("3", float(defaultQty) / 100)
        else:
            raise Exception("默认下单量类型异常")

        # 最小下单量
        self._strConfig.setMinQty(int(minQty))
        # 投保标志
        # if hedge == "投机":
        #     self._strConfig.setHedge("T")
        # elif hedge == "套利":
        #     self._strConfig.setHedge("B")
        # elif hedge == "保值":
        #     self._strConfig.setHedge("S")
        # elif hedge == "做市":
        #     self._strConfig.setHedge("M")
        # else:
        #     raise Exception("投保标志异常")

        # # 保证金率
        # TODO: margin类型没有设置！！！！！
        # 比例
        self._strConfig.setMargin('R', float(margin) / 100)

        # 开仓按比例收费
        if openType == "比例":
            self._strConfig.setTradeFee('O', 'R', float(openFee) / 100)
        else:
            self._strConfig.setTradeFee('O', 'F', float(openFee))
        # 平仓按比例收费
        if closeType == "比例":
            self._strConfig.setTradeFee('C', 'R', float(closeFee) / 100)
        else:
            self._strConfig.setTradeFee('C', 'F', float(closeFee))
        # 平今手续费
        # TODO：平今手续费没有设置
        # self.config["Money"]["CloseTodayFee"]["Type"] = "F"
        # self.config["Money"]["CloseTodayFee"]["Type"] = 0
        self._strConfig.setTradeFee('T', "F", 0)

        # 滑点损耗
        self._strConfig.setSlippage(float(slippage))

        # 发单设置
        openT = int(openTimes) if isOpenTimes else -1  # 每根K线同向开仓次数
        cOpenT = int(conOpenTimes) if isConOpenTimes else -1  # 最大连续同向开仓次数
        self._strConfig.setLimit(openT, cOpenT, canClose, canOpen)

        # 用户参数
        params = {}
        for i in range(self.paramsTableWidget.rowCount()):
            paramValues = []
            for j in range(self.paramsTableWidget.columnCount()):
                paramValues.append(self.paramsTableWidget.item(i, j).text())
            temp = paramValues[1]
            if paramValues[2] == "bool":
                if paramValues[1] == "True":
                    temp = True
                elif paramValues[1] == "False":
                    temp = False

            # TODO: 字符串转换时很麻烦
            if paramValues[2] == "str" or paramValues[2] == "bool" or paramValues[2] == "int":
                params[paramValues[0]] = (eval(paramValues[2])(temp), paramValues[3])
                continue
            else:
                params[paramValues[0]] = (eval(paramValues[2])(eval(temp)), paramValues[3])

        self._strConfig.setParams(params)

        # ----------------持仓设置-------------------
        pos_config = self.readPositionConfig()
        self._strConfig.setAutoSyncPos(pos_config)

        self.config = self._strConfig.getConfig()
        # print("-----------: ", self.config)

        # -------------保存用户配置--------------------------
        # strategyPath = self._control.getEditorText()["path"]
        strategyPath = self._strategyPath
        userConfig = {
            strategyPath: {
                VUser: user,
                VInitFund: initFund,
                VDefaultType: defaultType,
                VDefaultQty: defaultQty,
                VMinQty: minQty,
                # VHedge: hedge,
                VMargin: margin,
                VOpenType: openType,
                VCloseType: closeType,
                VOpenFee: openFee,
                VCloseFee: closeFee,
                VDirection: tradeDirection,
                VSlippage: slippage,
                VTimer: timer,
                VIsCycle: isCycle,
                VCycle: cycle,
                VIsKLine: isKLine,
                VIsMarket: isSnapShot,
                VIsTrade: isTrade,

                # VSampleVar: sampleVar,
                # VBeginDate: beginDate,
                # VFixQty: fixQty,

                VSendOrderMode: sendOrderMode,
                VIsActual: isActual,
                VIsAlarm: isAlarm,
                VIsPop: isPop,
                VIsOpenTimes: isOpenTimes,
                VOpenTimes: openTimes,
                VIsConOpenTimes: isConOpenTimes,
                VConOpenTimes: conOpenTimes,
                VCanClose: canClose,
                VCanOpen: canOpen,

                # VParams: params,
                VContSettings: contsInfo
            }
        }

        # 将配置信息保存到本地文件
        self.writeConfig(userConfig)
        config = self.getConfig()
        if config:  # 获取到config
            if self.contractWin.row == -1:
                self._control._request.loadRequest(strategyPath, config)
                self._control.logger.info("load strategy")
            else:
                self._control._request.strategyParamRestart(self._paramFlag, config)
                self._control.logger.info("Restarting strategy by new paramters")
        self.close()

    def readConfig(self):
        """读取配置文件"""
        if os.path.exists(r"./config/loadconfigure.json"):
            with open(r"./config/loadconfigure.json", "r", encoding="utf-8") as f:
                try:
                    result = json.loads(f.read())
                except json.decoder.JSONDecodeError:
                    return None
                else:
                    return result
        else:
            filePath = os.path.abspath(r"./config/loadconfigure.json")
            f = open(filePath, 'w')
            f.close()

    def writeConfig(self, configure):
        """写入配置文件"""
        # 将文件内容追加到配置文件中
        try:
            config = self.readConfig()
        except:
            config = None
        if config:
            for key in configure:
                config[key] = configure[key]
                break
        else:
            config = configure

        with open(r"./config/loadconfigure.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(config, indent=4))

    def readPositionConfig(self):
        """读取持仓配置文件"""
        if os.path.exists(r"./config/loadpositionon.json"):
            with open(r"./config/loadpositionon.json", "r", encoding="utf-8") as f:
                try:
                    result = json.loads(f.read())
                except json.decoder.JSONDecodeError:
                    return None
                else:
                    return result
        else:
            filePath = os.path.abspath(r"./config/loadpositionon.json")
            f = open(filePath, 'w')
            f.close()

    def getConfig(self):
        """获取用户配置的config"""
        return self.config

    def getTextConfigure(self):
        """从配置文件中得到配置信息"""
        try:
            configure = self.readConfig()
        except EOFError:
            configure = None

        # key = self._control.getEditorText()["path"]
        key = self._strategyPath
        if configure:
            if key in configure:
                return configure[key]
        return None

    def setDefaultConfigure(self):
        conf = self.getTextConfigure()
        if conf:
            # self.user.set(conf[VUser]),
            self.initFundlineEdit.setText(conf[VInitFund]),
            self.defaultOrderComboBox.setCurrentText(conf[VDefaultType]),
            self.defaultOrderLineEdit.setText(conf[VDefaultQty]),
            self.miniOrderLineEdit.setText(conf[VMinQty]),
            # self.hedge.set(conf[VHedge]),
            self.marginRateLineEdit.setText(conf[VMinQty]),

            self.openTypeComboBox.setCurrentText(conf[VOpenType]),
            self.closeTypeComboBox.setCurrentText(conf[VCloseType]),
            self.openFeeRateLineEdit.setText(conf[VOpenFee]),
            self.closeFeeRateLineEdit.setText(conf[VCloseFee]),
            self.tradeDirectionComboBox.setCurrentText(conf[VDirection]),
            self.slippageLineEdit.setText(conf[VSlippage]),

            self.cycleCheckBox.setChecked(conf[VIsCycle]),
            self.cycleLineEdit.setText(conf[VCycle]),

            # 定时触发通过函数设置
            for t in conf[VTimer].split('\n'):
                self.timerListWidget.addItem(t)   # todo

            self.KLineCheckBox.setChecked(conf[VIsKLine]),
            self.snapShotCheckBox.setChecked(conf[VIsMarket]),
            self.tradeCheckBox.setChecked(conf[VIsTrade]),

            # self.sampleVar.set(conf[VSampleVar]),
            # self.beginDate.set(conf[VBeginDate]),
            # self.fixQty.set(conf[VFixQty]),

            if conf[VSendOrderMode]:
                self.sendOrderRealtime.setChecked(False)
                self.sendOrderKStable.setChecked(True)
            else:
                self.sendOrderRealtime.setChecked(True)
                self.sendOrderKStable.setChecked(False)
            self.actualCheckBox.setChecked(conf[VIsActual]),
            try:
                self.alarmCheckBox.setChecked(conf[VIsAlarm])
            except KeyError as e:
                self.alarmCheckBox.setChecked(0)

            try:
                self.allowCheckBox.setChecked(conf[VIsPop])
            except KeyError as e:
                self.allowCheckBox.setChecked(0)

            self.openTimesCheckBox.setChecked(conf[VIsOpenTimes]),
            self.openTimeslineEdit.setText(conf[VOpenTimes]),
            self.isConOpenTimesCheckBox.setChecked(conf[VIsConOpenTimes]),
            self.isConOpenTimesLineEdit.setText(conf[VConOpenTimes]),
            self.canCloseCheckBox.setChecked(conf[VCanClose]),
            self.canOpenCheckBox.setChecked(conf[VCanOpen]),

            # 用户配置参数信息
            # 若保存的设置中用户参数为空，则不对self._userParam赋值
            try:
                if conf[VParams]:
                    self._userParam = conf[VParams]
                    for v in self._userParam:
                        self.insert_params(v)
            except KeyError as e:
                pass
                # traceback.print_exc()
            # TODO: DefaultSample
            try:
                if conf[VContSettings]:
                    self._contsInfo = conf[VContSettings]
                    for v in self._contsInfo:
                        self.insert_contract_row(v)
            except KeyError as e:
                pass
                # traceback.print_exc()

    def insert_contract_row(self, values):
        """在合约table中插入一行"""
        row = self.contractTableWidget.rowCount()
        self.contractTableWidget.setRowCount(row + 1)
        for j in range(len(values)):
            item = QTableWidgetItem(str(values[j]))
            self.contractTableWidget.setItem(row, j, item)

    def insert_params(self, values):
        """在参数table中插入一行"""
        row = self.paramsTableWidget.rowCount()
        self.paramsTableWidget.setRowCount(row + 1)
        for j in range(len(values)):
            item = QTableWidgetItem(str(values(j)))
            self.paramsTableWidget.setItem(row, j, item)


class ContractWin(QMainWindow, Ui_contractWin):
    confirm_signal = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.kLineTypeComboBox.currentIndexChanged.connect(self.valid)
        self.qtylineEdit.setValidator(QtGui.QIntValidator())
        self.confirm.clicked.connect(self.valid_contract)
        self.cancel.clicked.connect(self.close)
        self.row = -1

    def valid(self, index):
        if index == 0:
            self.kLinePeriodComboBox.setEnabled(False)
        else:
            self.kLinePeriodComboBox.setEnabled(True)

    def valid_contract(self):
        if not self.contractCodeLineEdit.text():
            QMessageBox.warning(self, '提示', '请先选择合约！！！', QMessageBox.Yes)
            return
        if self.startDateRadioButton.isChecked():
            try:
                assert len(self.startDateLineEdit.text()) == 8
            except:
                QMessageBox.warning(self, '提示', '输入的时间格式不合法，请重新输入！！！', QMessageBox.Yes)
                return
        self.confirm_signal.emit(self.get_contract_policy())
        self.close()

    def get_contract_policy(self):
        """获取商品属性"""
        kLineCount = 0
        beginTime = ''
        allK = False
        useSample = False
        # ----------------商品代码-------------------
        contract = self.contractCodeLineEdit.text()

        # ----------------K线类型--------------------
        index = self.kLineTypeComboBox.currentIndex()
        rule = {0: 'T', 1: 'S', 2: 'M', 3: 'D'}
        KLineType = rule.get(index)

        # ----------------K线周期--------------------
        KLineSlice = self.kLinePeriodComboBox.currentText()
        if KLineType == 'T':
            KLineSlice = 0
        # TODO K线选择分笔时候K线周期应传的值

        # ----------------运算起始点-----------------
        if self.AllkLineRadioButton.isChecked():
            allK = True
        elif self.startDateRadioButton.isChecked():
            beginTime = self.startDateLineEdit.text()
        elif self.qtyRadioButton.isChecked():
            kLineCount = int(self.qtylineEdit.text())
        elif self.historyRadioButton.isChecked():
            useSample = True  # TODO 选中不执行历史K线时候的值为False还是True

        return {
            'row': self.row,  # 标志位，为-1是新增合约，其他为更新合约
            'contract': contract,
            'KLineType': KLineType,
            'KLineSlice': KLineSlice,
            'BeginTime': beginTime,  # 运算起始点-起始日期
            'KLineCount': kLineCount,  # 运算起始点-固定根数
            'AllK': allK,  # 运算起始点-所有K线
            'UseSample': useSample,  # 运算起始点-不执行历史K线
            # 'Trigger': trigger     # 是否订阅历史K线  TODO trigger
        }


class ContractSelect(QMainWindow, Ui_contractSelect):
    exchangeList = ["SPD", "ZCE", "DCE", "SHFE", "INE", "CFFEX",
                    "CME", "COMEX", "LME", "NYMEX", "HKEX", "CBOT", "ICUS", "ICEU", "SGX"]
    commodityType = {"P": "现货", "Y": "现货", "F": "期货", "O": "期权",
                     "S": "跨期套利", "M": "品种套利", "s": "", "m": "",
                     "y": "", "T": "股票", "X": "外汇",
                     "I": "外汇", "C": "外汇"}
    # 外盘保留品种
    FCommodity = {"NYMEX": ["美原油"],
                  "COMEX": ["美铜", "美黄金"],
                  "HKEX": ["恒指", "小恒指", "H股指", "美元兑人民币", "小H股指"],
                  "CME": ["小标普", "小纳指"],
                  "CBOT": ["小道指", "美黄豆", "美豆粕", "美玉米"],
                  "ICUS": ["糖11号", "美棉花"],
                  "ICEU": ["布伦特原油", "富时指数"],
                  "SGX": ["A50指数"]}

    def __init__(self, exchange, commodity, contract, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.contract_tree.setColumnCount(2)
        self.contract_tree.setHeaderHidden(True)
        self.contract_tree.hideColumn(1)
        self.contract_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.contract_child_tree.setColumnCount(1)
        self.contract_child_tree.setHeaderHidden(True)
        self.choice_tree.setColumnCount(1)
        self.choice_tree.setHeaderHidden(True)
        self.contract_tree.clicked.connect(self.load_child_contract)  # 加载分类下的合约
        self.choice_tree.doubleClicked.connect(self.clear_choice)  # 双击选择的合约
        self.contract_child_tree.doubleClicked.connect(self.load_choice)
        self.cancel.clicked.connect(self.close)

        self._exchange = pd.DataFrame(exchange).drop_duplicates()
        self._commodity = pd.DataFrame(commodity, columns=["CommodityNo", "CommodityName"]).drop_duplicates()
        self._contract = pd.DataFrame(contract, columns=["ContractNo"]).drop_duplicates()
        self.load_contract()

    def load_contract(self):
        for exchangeNo in self.exchangeList:
            exchange = self._exchange.loc[self._exchange.ExchangeNo == exchangeNo]
            root = QTreeWidgetItem(self.contract_tree)
            self.contract_tree.hideColumn(1)
            for _, exch in exchange.iterrows():
                exName = exch.ExchangeNo + "【" + exch.ExchangeName + "】"
                root.setText(0, exName)
                root.setText(1, exch.ExchangeNo)

            ePattern = r"\A" + exchangeNo
            commodity = self._commodity.loc[self._commodity.CommodityNo.str.contains(ePattern)]
            for _, comm in commodity.iterrows():
                # 仅保留外盘支持的品种
                if exchangeNo in self.FCommodity:
                    if comm.CommodityName not in self.FCommodity[exchangeNo]:
                        continue

                tempComm = comm.CommodityNo.split("|")
                if tempComm[1] in self.commodityType.keys():
                    if tempComm[0] == "SPD":
                        text = comm.CommodityName
                    else:
                        text = comm.CommodityName + " [" + self.commodityType[tempComm[1]] + "]"
                    child = QTreeWidgetItem(root)
                    child.setText(0, text)
                    child.setText(1, comm.CommodityNo)
        # for contract in ['ZCE【郑商所】', 'DCE【大商所】']:
        #     root = QTreeWidgetItem(self.contract_tree)
        #     root.setText(0, contract)
        #     for child_contract in ['苹果', '棉花', '红枣']:
        #         child = QTreeWidgetItem(root)
        #         child.setText(0, child_contract)

    def load_child_contract(self):
        self.contract_child_tree.clear()
        items = self.contract_tree.selectedItems()
        for item in items:
            commodityNo = []
            exchangeNo = []
            if item.parent():
                commodityNo.append(item.text(1))
                exchangeNo.append(item.parent().text(1))
                commodityNoZ = commodityNo[0]
                temp = commodityNo[0].split("|")
                if temp[1] == "F":
                    temp[1] = "Z"
                    commodityNoZ = "|".join(temp)

                ePattern = r"\A" + exchangeNo[0] + "\|"
                cPattern = r"\A" + "\|".join(commodityNo[0].split("|")) + "\|"
                cZPattern = r"\A" + "\|".join(commodityNoZ.split("|")) + "\|"
                contract = self._contract.loc[
                    (self._contract.ContractNo.str.contains(ePattern))
                    & (
                            (self._contract.ContractNo.str.contains(cPattern))
                            |
                            (self._contract.ContractNo.str.contains(cZPattern))
                    )
                    ]
                for index, row in contract.iterrows():
                    root = QTreeWidgetItem(self.contract_child_tree)
                    root.setText(0, row["ContractNo"])

    def load_choice(self):
        item = self.contract_child_tree.currentItem()
        if self.choice_tree.topLevelItemCount() == 0:
            root = QTreeWidgetItem(self.choice_tree)
            root.setText(0, item.text(0))
        else:
            QMessageBox.warning(self, '提示', '选择的合约数不能超过1个！！！', QMessageBox.Yes)
        pass

    def clear_choice(self):
        self.choice_tree.clear()


class WebEngineView(QWebEngineView):
    customSignal = pyqtSignal(str, str)
    saveSignal = pyqtSignal()
    switchSignal = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super(WebEngineView, self).__init__(*args, **kwargs)
        self.initSettings()
        self.channel = QWebChannel(self)
        # 把自身对象传递进去
        self.channel.registerObject('Bridge', self)
        # 设置交互接口
        self.page().setWebChannel(self.channel)

        # START #####以下代码可能是在5.6 QWebEngineView刚出来时的bug,必须在每次加载页面的时候手动注入
        #### 也有可能是跳转页面后就失效了，需要手动注入，有没有修复具体未测试

    #         self.page().loadStarted.connect(self.onLoadStart)
    #         self._script = open('Data/qwebchannel.js', 'rb').read().decode()

    #     def onLoadStart(self):
    #         self.page().runJavaScript(self._script)

    # END ###########################

    # 注意pyqtSlot用于把该函数暴露给js可以调用
    @pyqtSlot(str, str)
    def callFromJs(self, file, text):
        try:
            with open(file, mode='w', encoding='utf-8') as f:
                f.write(text.replace('\r', ''))
                f.close()
        except Exception as e:
            print(e)

    def sendCustomSignal(self, file):
        # 发送自定义信号
        with open(file, 'r', encoding='utf-8') as f:
            text = f.read()
        self.customSignal.emit(file, text)

    def sendSaveSignal(self):
        self.saveSignal.emit()

    @pyqtSlot(str)
    def switchFile(self, path):
        """编辑器切换tab时候发信号到app修改策略路径"""
        self.switchSignal.emit(path)

    @pyqtSlot(str)
    @pyqtSlot(QUrl)
    def load(self, url):
        '''
        eg: load("https://pyqt5.com")
        :param url: 网址
        '''
        return super(WebEngineView, self).load(QUrl(url))

    def initSettings(self):
        '''
        eg: 初始化设置
        '''
        # 获取浏览器默认设置
        settings = QWebEngineSettings.globalSettings()
        # 设置默认编码utf8
        settings.setDefaultTextEncoding("utf-8")
        # 自动加载图片,默认开启
        # settings.setAttribute(QWebEngineSettings.AutoLoadImages,True)
        # 自动加载图标,默认开启
        # settings.setAttribute(QWebEngineSettings.AutoLoadIconsForPage,True)
        # 开启js,默认开启
        # settings.setAttribute(QWebEngineSettings.JavascriptEnabled,True)
        # js可以访问剪贴板
        settings.setAttribute(
            QWebEngineSettings.JavascriptCanAccessClipboard, True)
        # js可以打开窗口,默认开启
        # settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows,True)
        # 链接获取焦点时的状态,默认开启
        # settings.setAttribute(QWebEngineSettings.LinksIncludedInFocusChain,True)
        # 本地储存,默认开启
        # settings.setAttribute(QWebEngineSettings.LocalStorageEnabled,True)
        # 本地访问远程
        settings.setAttribute(
            QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        # 本地加载,默认开启
        # settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls,True)
        # 监控负载要求跨站点脚本,默认关闭
        # settings.setAttribute(QWebEngineSettings.XSSAuditingEnabled,False)
        # 空间导航特性,默认关闭
        # settings.setAttribute(QWebEngineSettings.SpatialNavigationEnabled,False)
        # 支持平超链接属性,默认关闭
        # settings.setAttribute(QWebEngineSettings.HyperlinkAuditingEnabled,False)
        # 使用滚动动画,默认关闭
        settings.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)
        # 支持错误页面,默认启用
        # settings.setAttribute(QWebEngineSettings.ErrorPageEnabled, True)
        # 支持插件,默认关闭
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        # 支持全屏应用程序,默认关闭
        settings.setAttribute(
            QWebEngineSettings.FullScreenSupportEnabled, True)
        # 支持屏幕截屏,默认关闭
        settings.setAttribute(QWebEngineSettings.ScreenCaptureEnabled, True)
        # 支持html5 WebGl,默认开启
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, True)
        # 支持2d绘制,默认开启
        settings.setAttribute(
            QWebEngineSettings.Accelerated2dCanvasEnabled, True)
        # 支持图标触摸,默认关闭
        settings.setAttribute(QWebEngineSettings.TouchIconsEnabled, True)


class QuantApplication(QWidget):
    def __init__(self, control, parent=None):
        super().__init__(parent)

        # 初始化控制器
        self._controller = control
        self._logger = self._controller.get_logger()

        self.hbox = QHBoxLayout()

        # self.topLayout = QGridLayout()  # 上方布局
        # self.bottomLayout = QGridLayout()  # 下方布局
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.left_splitter = QSplitter(Qt.Vertical)
        self.right_splitter = QSplitter(Qt.Vertical)

        self.left_top_splitter = QSplitter(Qt.Horizontal)

        # 获取所有策略可用过滤规则及目录
        self.strategy_filter = get_strategy_filters(strategy_path)

        self.create_stragety_vbox()
        self.create_content_vbox()
        self.create_func_tab()
        self.create_tab()
        self.create_func_doc()
        # self.mainLayout = QGridLayout()  # 主布局为垂直布局
        # self.mainLayout.setSpacing(5)  # 主布局添加补白
        screen = QDesktopWidget().screenGeometry()  # 获取电脑屏幕分辨率
        width = screen.width()
        height = screen.height()
        # 左上部布局
        self.left_top_splitter.addWidget(self.strategy_vbox)
        self.left_top_splitter.addWidget(self.content_vbox)
        self.left_top_splitter.setSizes([width * 0.8 * 0.2, width * 0.8 * 0.6])

        # 左部布局
        self.left_splitter.addWidget(self.left_top_splitter)
        self.left_splitter.addWidget(self.tab_widget)
        self.left_splitter.setSizes([height * 0.8 * 0.4, height * 0.8 * 0.1])

        # 右部布局
        self.right_splitter.addWidget(self.func_tab)
        self.right_splitter.addWidget(self.func_doc)
        self.right_splitter.setSizes([height * 0.8 * 0.3, height * 0.8 * 0.1])

        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setSizes([width * 0.8 * 0.4, width * 0.8 * 0.1])

        self.hbox.addWidget(self.main_splitter)
        self.setLayout(self.hbox)
        # self.setGeometry(screen.width() * 0.1, screen.height() * 0.1, screen.width() * 0.8,
        #                  screen.height() * 0.8)  # 设置居中和窗口大小
        # self.setWindowTitle('极星量化')
        # self.setWindowIcon(QIcon('icon/epolestar ix2.ico'))
        self.setWindowFlags(Qt.FramelessWindowHint)
        # self.show()

        # 策略信息
        self.strategy_path = None

        # with open(r'ui/qdark.qss', encoding='utf-8') as f:
        #     self.setStyleSheet(f.read())
        # self.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._controller.update_log)
        self.timer.timeout.connect(self._controller.update_mon)
        self.timer.start(1000)

    def closeEvent(self, event):
        # 退出子线程和主线程
        self._controller.sendExitRequest()
        self._controller.quitThread()

    def init_control(self):
        self._exchange = self._controller.model.getExchange()
        self._commodity = self._controller.model.getCommodity()
        self._contract = self._controller.model.getContract()
        self._userNo = self._controller.model.getUserNo()

    def create_stragety_vbox(self):
        # 策略树
        self.strategy_vbox = QFrame()
        label = QLabel('策略')
        self.strategy_layout = QVBoxLayout()
        self.model = QFileSystemModel()
        self.strategy_tree = Tree(self.model, self.strategy_filter)
        # self.strategy_tree = Tree(strategy_path)
        self.model.setRootPath(QtCore.QDir.rootPath())
        self.strategy_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.strategy_tree.setModel(self.model)
        self.strategy_tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.strategy_tree.setRootIndex(self.model.index(strategy_path))
        # self.strategy_tree.setColumnCount(1)
        self.model.setReadOnly(False)
        self.model.setNameFilters(self.strategy_filter)
        self.model.setNameFilterDisables(False)
        self.model.setFilter(QDir.Dirs | QDir.Files)
        # self.strategy_tree.setHeaderLabels(['策略'])
        self.strategy_tree.setHeaderHidden(True)
        self.strategy_tree.hideColumn(1)
        self.strategy_tree.hideColumn(2)
        self.strategy_tree.hideColumn(3)

        self.strategy_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.strategy_tree.customContextMenuRequested[QPoint].connect(self.strategy_tree_right_menu)

        self.strategy_tree.doubleClicked.connect(self.strategy_tree_clicked)
        self.strategy_layout.addWidget(label)
        self.strategy_layout.addWidget(self.strategy_tree)
        self.strategy_vbox.setLayout(self.strategy_layout)

    # 策略右键菜单
    def strategy_tree_right_menu(self, point):
        self.strategy_tree.popMenu = QMenu()
        self.strategy_tree.addType = QMenu(self.strategy_tree.popMenu)
        self.strategy_tree.addType.setTitle('新建')
        import_file = QAction('导入')
        rename = QAction('重命名', self.strategy_tree)
        delete = QAction('删除', self.strategy_tree)
        add_strategy = QAction('新建策略')
        add_group = QAction('新建分组')
        refresh = QAction('刷新', self.strategy_tree)
        self.strategy_tree.popMenu.addAction(import_file)
        self.strategy_tree.popMenu.addMenu(self.strategy_tree.addType)
        self.strategy_tree.addType.addAction(add_strategy)
        self.strategy_tree.addType.addAction(add_group)
        self.strategy_tree.popMenu.addAction(rename)
        self.strategy_tree.popMenu.addAction(delete)
        self.strategy_tree.popMenu.addAction(refresh)

        # 右键动作
        action = self.strategy_tree.popMenu.exec_(self.strategy_tree.mapToGlobal(point))
        if action == import_file:
            index = self.strategy_tree.currentIndex()
            model = index.model()  # 请注意这里可以获得model的对象
            item_path = model.filePath(index)
            if item_path:
                if not os.path.isdir(item_path):
                    item_path = os.path.split(item_path)[0]
                desktop = os.path.join(os.path.expanduser("~"), 'Desktop')
                fname, ftype = QFileDialog.getOpenFileName(self, "打开...", desktop, "python文件(*.py *pyw)")
                if fname:
                    _path = item_path + '/' + os.path.split(fname)[1]
                    if os.path.exists(_path):
                        reply = QMessageBox.question(self, '提示', '所选的分组中存在同名文件，是否覆盖？', QMessageBox.Yes | QMessageBox.No)
                        if reply == QMessageBox.Yes:
                            shutil.copy(fname, _path)
                    else:
                        shutil.copy(fname, _path)
                    self.contentEdit.sendCustomSignal(_path)
        elif action == add_strategy:
            index = self.strategy_tree.currentIndex()
            model = index.model()  # 请注意这里可以获得model的对象
            item_path = model.filePath(index)
            if item_path and os.path.isdir(item_path):
                value = ''
                while True:
                    value, ok = QInputDialog.getText(self, '新建文件', '策略名称', QLineEdit.Normal)
                    path = os.path.join(item_path, value + '.py')
                    if os.path.exists(path) and ok:
                        QMessageBox.warning(self, '提示', '策略名在选择的分组%s已经存在！！！' % value, QMessageBox.Yes)
                    elif not ok:
                        break
                    else:
                        with open(path, 'w', encoding='utf-8') as w:
                            pass
                        break
            elif not os.path.isdir(item_path):
                value = ''
                while True:
                    value, ok = QInputDialog.getText(self, '新建文件', '策略名称', QLineEdit.Normal)
                    path = os.path.join(os.path.split(item_path)[1], value + '.py')
                    if os.path.exists(path) and ok:
                        QMessageBox.warning(self, '提示', '策略名在选择的分组%s已经存在！！！' % value, QMessageBox.Yes)
                    elif not ok:
                        break
                    else:
                        with open(path, 'w', encoding='utf-8') as w:
                            pass
                        break
            else:
                QMessageBox.warning(self, '提示', '请选择分组！！！', QMessageBox.Yes)

        elif action == add_group:
            value = ''
            flag = self.strategy_tree.indexAt(point)  # 判断鼠标点击位置标志位
            while True:
                if not flag.isValid():  # 鼠标点击位置不在目录树叶子上
                    item_path = strategy_path  # 新建文件夹位置在根目录
                else:
                    index = self.strategy_tree.currentIndex()
                    model = index.model()  # 请注意这里可以获得model的对象
                    item_path = model.filePath(index)
                value, ok = QInputDialog.getText(self, '新建文件夹', '分组名称', QLineEdit.Normal, value)
                if os.path.isdir(item_path):
                    path = os.path.join(item_path, value)
                else:
                    path = os.path.join(os.path.split(item_path)[0], value)
                if os.path.exists(path) and ok:
                    QMessageBox.warning(self, '提示', '分组%s已经存在！！！' % value, QMessageBox.Yes)
                elif not ok:
                    break
                else:
                    os.mkdir(path)
                    self.strategy_filter.append(os.path.split(path)[1])
                    self.model.setNameFilters(self.strategy_filter)
                    break

        elif action == refresh:
            index = self.strategy_tree.currentIndex()
            model = index.model()  # 请注意这里可以获得model的对象
            model.dataChanged.emit(index, index)
        elif action == rename:
            index = self.strategy_tree.currentIndex()
            model = index.model()  # 请注意这里可以获得model的对象
            item_path = model.filePath(index)
            if not os.path.isdir(item_path):  # 修改策略名
                value = ''
                (file_path, filename) = os.path.split(item_path)
                while True:
                    value, ok = QInputDialog.getText(self, '修改%s策略名' % filename, '策略名称', QLineEdit.Normal, value)
                    new_path = os.path.join(file_path, value + '.py')
                    if os.path.exists(new_path) and ok:
                        QMessageBox.warning(self, '提示', '策略名在此分组中%s已经存在！！！' % value, QMessageBox.Yes)
                    elif not ok:
                        break
                    else:
                        os.rename(item_path, new_path)
                        break
            else:
                value = ''
                (dir_path, dir_name) = os.path.split(item_path)
                while True:
                    value, ok = QInputDialog.getText(self, '修改%s文件夹' % dir_name, '分组名称', QLineEdit.Normal, value)
                    new_path = os.path.join(dir_path, value)
                    if os.path.exists(new_path) and ok:
                        QMessageBox.warning(self, '提示', '分组%s已经存在！！！' % value, QMessageBox.Yes)
                    elif not ok:
                        break
                    else:
                        os.rename(item_path, new_path)
                        break
        elif action == delete:
            index = self.strategy_tree.currentIndex()
            model = index.model()  # 请注意这里可以获得model的对象
            item_path = model.filePath(index)
            if item_path and os.path.isdir(item_path):
                reply = QMessageBox.question(self, '提示', '确定删除分组及目录下的所有文件吗？', QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    shutil.rmtree(item_path)
                    self.strategy_filter.remove(os.path.split(item_path)[1])
            elif item_path and not os.path.isdir(item_path):
                reply = QMessageBox.question(self, '提示', '确定删除文件%s吗？' % item_path, QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    os.remove(item_path)
            else:
                pass
        else:
            pass

    def create_content_vbox(self):
        # self.content_vbox = QGroupBox('内容')
        self.content_vbox = QWidget()
        self.content_layout = QGridLayout()
        self.save_btn = QPushButton('保存')
        self.run_btn = QPushButton('运行')
        self.run_btn.setEnabled(False)
        # self.contentEdit = MainFrmQt("localhost", 8765, "pyeditor", os.path.join(os.getcwd(), 'quant\python_editor\editor.htm'))
        self.contentEdit = WebEngineView()
        self.contentEdit.load(
            QUrl.fromLocalFile(os.path.abspath(r'qtui/quant/python_editor/editor.htm')))
        self.contentEdit.switchSignal.connect(self.switch_strategy_path)
        self.statusBar = QLabel()
        self.statusBar.setStyleSheet('border: none;')

        self.save_btn.setMaximumSize(40, 30)
        self.run_btn.setMaximumSize(40, 30)
        self.content_layout.addWidget(self.statusBar, 0, 0, 1, 1)
        self.content_layout.addWidget(self.run_btn, 1, 1, 1, 1)
        self.content_layout.addWidget(self.save_btn, 1, 2, 1, 1)
        self.content_layout.addWidget(self.contentEdit, 2, 0, 20, 3)
        self.content_vbox.setLayout(self.content_layout)
        self.run_btn.clicked.connect(lambda: self.create_strategy_policy_win({}, self.strategy_path, False))
        self.save_btn.clicked.connect(self.emit_custom_signal)

    def switch_strategy_path(self, path):
        self.strategy_path = path

    def set_run_btn_state(self, status):
        """
        设置运行按钮是否可用
        :param status: bool  (True: 可用, False: 不可用)
        :return:
        """
        self.run_btn.setEnabled(status)

    def emit_custom_signal(self):
        self.contentEdit.sendSaveSignal()

    def create_func_tab(self):
        # 函数列表
        # self.func_vbox = QGroupBox('函数')
        self.func_tab = QTabWidget()  # 通过tab切换目录、检索
        self.search_widget = QWidget()
        self.func_layout = QVBoxLayout()
        self.func_layout.setSpacing(0)
        self.func_layout.setContentsMargins(0, 5, 0, 0)

        # 函数树结构
        self.func_tree = QTreeWidget()
        self.func_tree.setColumnCount(2)
        self.func_tree.setHeaderLabels(['函数名', '函数介绍'])
        self.func_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)  # 设置列宽自适应
        self.func_tree.setHeaderHidden(True)
        for k, v in _all_func_.items():
            root = QTreeWidgetItem(self.func_tree)
            root.setText(0, k)
            root.setText(1, '')
            for i in v:
                child = QTreeWidgetItem(root)
                child.setText(0, i[0])
                child.setText(1, i[1])
        self.func_tree.clicked.connect(self.func_tree_clicked)

        # 函数检索
        self.search_line = QLineEdit()
        self.search_line.setPlaceholderText('请输入要搜索的函数名或介绍')
        self.search_line.textChanged.connect(self.search)
        # self.func_table = QTableWidget()
        # self.func_table.setColumnCount(2)

        # table数据
        func_list = []
        for k, v in _all_func_.items():
            func_list.extend(v)
        func_list.sort(key=lambda x: x[0])
        # self.func_table.setColumnCount(2)
        # self.func_table.setRowCount(len(func_list))
        # self.func_table.setHorizontalHeaderLabels(['函数名', '函数介绍'])
        # self.func_table.verticalHeader().setVisible(False)
        #
        # for i in range(len(func_list)):
        #     for j in range(len(func_list[i])):
        #         item = QTableWidgetItem(func_list[i][j])
        #         self.func_table.setItem(i, j, item)

        #######################################################
        self.search_tree = QTreeWidget()
        self.search_tree.setColumnCount(2)
        self.search_tree.setHeaderLabels(['函数名', '函数介绍'])
        self.search_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.search_tree.setHeaderHidden(True)
        self.search_tree.clicked.connect(self.search_tree_clicked)

        # self.func_tree.setHeaderHidden(True)
        for v in func_list:
            root = QTreeWidgetItem(self.search_tree)
            root.setText(0, v[0])
            root.setText(1, v[1])
        # self.search_tree.setStyleSheet("branch {image:none;}")
        #######################################################

        self.func_layout.addWidget(self.search_line)
        self.func_layout.addWidget(self.search_tree)
        self.search_widget.setLayout(self.func_layout)

        self.func_tab.addTab(self.func_tree, '函数目录')
        self.func_tab.addTab(self.search_widget, '函数检索')

        # self.func_layout.addWidget(self.func_tab)
        # self.func_vbox.setLayout(self.func_layout)

    def create_tab(self):
        self.tab_widget = QTabWidget()
        # 策略运行table
        self.strategy_table = QTableWidget()
        self.strategy_table.setRowCount(0)  # 行数
        self.strategy_table.setColumnCount(12)  # 列数
        self.strategy_table.verticalHeader().setVisible(False)
        self.strategy_table.setShowGrid(False)
        # self.strategy_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)  # 所有列自动拉伸，充满界面
        self.strategy_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)  # 所有列自动拉伸，充满界面
        self.strategy_table.setSelectionMode(QAbstractItemView.SingleSelection)  # 设置只能选中一行
        self.strategy_table.setEditTriggers(QTableView.NoEditTriggers)  # 不可编辑
        self.strategy_table.setSelectionBehavior(QAbstractItemView.SelectRows)  # 设置只有行选中
        self.strategy_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.strategy_table.setHorizontalHeaderLabels(["编号", "账号", "策略名称", "基准合约", "频率", "运行阶段", "运行模式",
                                                       "初始资金", "可用资金", "最大回撤", "累计收益", "胜率"])

        # ----------------------日志tab----------------------------------
        self.log_widget = QTabWidget()
        self.log_widget.setTabPosition(QTabWidget.South)
        self.user_log_widget = QTextBrowser()
        self.signal_log_widget = QTextBrowser()
        self.sys_log_widget = QTextBrowser()
        self.log_widget.addTab(self.user_log_widget, '用户日志')
        self.log_widget.addTab(self.signal_log_widget, '信号日志')
        self.log_widget.addTab(self.sys_log_widget, '系统日志')
        self.log_widget.tabBarClicked.connect(self.loadSysLogFile)
        # self.log_widget.currentChanged.connect(self.loadSysLogFile)

        # -----------------设置文本框变化的时候滚动条自动滚动到最底部-------------------
        # self.sys_log_widget.textChanged.connect(lambda: self.sys_log_widget.moveCursor(QTextCursor.End))
        # self.sys_log_widget.moveCursor(QTextCursor.End)
        self.error_info_widget = QTextBrowser()

        # -------------------组合监控----------------------------
        self.union_monitor = QWidget()
        self.union_layout = QGridLayout()
        self.one_key_sync = QPushButton('持仓一键同步')
        self.cbComboBox = QComboBox()
        self.cbComboBox.addItems(['对盘价', '最新价', '市价'])
        self.cbComboBox.currentIndexChanged.connect(self.valid_spin)
        spacerItem = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        spacerItem2 = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.spin = QSpinBox()
        self.spin.setMinimum(1)
        self.spin.setMaximum(100)
        self.intervalCheckBox = QCheckBox('自动同步间隔')
        self.intervalCheckBox.stateChanged.connect(self.save_position_config)
        self.intervalCheckBox.stateChanged.connect(self.change_connection)  # 是否连接信号
        self.intervalSpinBox = QSpinBox()
        self.intervalSpinBox.setMinimum(500)
        self.intervalSpinBox.setMaximum(2147483647)
        self.intervalSpinBox.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.intervalSpinBox.setMinimumWidth(80)
        self.reducePositionCheckBox = QCheckBox('仅自动减仓')

        self.union_layout.addWidget(self.one_key_sync, 0, 0, 1, 1)
        self.union_layout.addItem(spacerItem2, 0, 1, 1, 1)
        self.union_layout.addWidget(QLabel('同步设置：'), 0, 2, 1, 1)
        self.union_layout.addWidget(self.cbComboBox, 0, 3, 1, 1)
        self.union_layout.addWidget(QLabel('+'), 0, 4, 1, 1)
        self.union_layout.addWidget(self.spin, 0, 5, 1, 1)
        self.union_layout.addWidget(QLabel('跳'), 0, 6, 1, 1)
        self.union_layout.addItem(spacerItem2, 0, 7, 1, 1)
        self.union_layout.addWidget(self.intervalCheckBox, 0, 8, 1, 1)
        self.union_layout.addWidget(self.intervalSpinBox, 0, 9, 1, 1)
        self.union_layout.addWidget(QLabel('毫秒'), 0, 10, 1, 1)
        self.union_layout.addItem(spacerItem2, 0, 11, 1, 1)
        self.union_layout.addWidget(self.reducePositionCheckBox, 0, 12, 1, 1)
        self.union_layout.addItem(spacerItem, 0, 13, 1, 1)
        self.union_layout.setSpacing(0)
        self.union_layout.setContentsMargins(0, 0, 0, 0)

        self.one_key_sync.clicked.connect(lambda: self.save_position_config(True))

        # -----根据loadPositionConfig设置持仓更新参数-------
        config = self.readPositionConfig()
        if not config:
            self.intervalSpinBox.setValue(5000)
            config = {
                'OneKeySync': False,  # 一键同步
                'AutoSyncPos': self.intervalCheckBox.isChecked(),  # 是否自动同步
                'PriceType': self.cbComboBox.currentIndex(),  # 价格类型 0:对盘价, 1:最新价, 2:市价
                'PriceTick': self.spin.value(),  # 超价点数
                'OnlyDec': self.reducePositionCheckBox.isChecked(),  # 是否只做减仓同步
                'SyncTick': self.intervalSpinBox.value(),  # 同步间隔，毫秒
            }
            self.writePositionConfig(config)
        else:
            self.intervalCheckBox.setChecked(config.get('AutoSyncPos'))
            self.cbComboBox.setCurrentIndex(config.get('PriceType'))
            self.spin.setValue(config.get('PriceTick'))
            self.reducePositionCheckBox.setChecked(config.get('OnlyDec'))
            self.intervalSpinBox.setValue(config.get('SyncTick'))
        # -----持仓信息--------------
        self.pos_table = QTableWidget()
        self.pos_table.setRowCount(0)  # 行数
        self.pos_table.setColumnCount(13)  # 列数
        self.pos_table.verticalHeader().setVisible(False)
        self.pos_table.setShowGrid(False)
        self.pos_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)  # 所有列自动拉伸，充满界面
        self.pos_table.setSelectionMode(QAbstractItemView.SingleSelection)  # 设置只能选中一行
        self.pos_table.setEditTriggers(QTableView.NoEditTriggers)  # 不可编辑
        self.pos_table.setSelectionBehavior(QAbstractItemView.SelectRows)  # 设置只有行选中
        self.pos_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.pos_table.setHorizontalHeaderLabels(["账号", "合约", "账户仓", "策略仓", "仓差",
                                                  "策略多", "策略空", "策略今多", "策略今空", "账户多", "账户空", "账户今多", "账户今空"])
        self.union_layout.addWidget(self.pos_table, 1, 0, 1, 14)
        self.union_monitor.setLayout(self.union_layout)

        self.tab_widget.addTab(self.strategy_table, "策略运行")  # 策略运行tab
        self.tab_widget.addTab(self.log_widget, "运行日志")  # 运行日志tab
        self.tab_widget.addTab(self.error_info_widget, "错误信息")  # 错误信息志tab
        self.tab_widget.addTab(self.union_monitor, "组合监控")  # 组合监控tab

        self.strategy_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.strategy_table.customContextMenuRequested[QPoint].connect(self.strategy_table_right_menu)

    def strategy_table_right_menu(self, point):
        self.strategy_table.popMenu = QMenu()
        run = QAction('启动', self.strategy_table)
        stop = QAction('停止', self.strategy_table)
        delete = QAction('删除', self.strategy_table)
        report = QAction('投资报告', self.strategy_table)
        onSignal = QAction('图表展示', self.strategy_table)
        policy = QAction('属性设置', self.strategy_table)
        selectAll = QAction('全选', self.strategy_table)

        self.strategy_table.popMenu.addAction(run)
        self.strategy_table.popMenu.addAction(stop)
        self.strategy_table.popMenu.addAction(delete)
        self.strategy_table.popMenu.addAction(report)
        self.strategy_table.popMenu.addAction(onSignal)
        self.strategy_table.popMenu.addAction(policy)
        self.strategy_table.popMenu.addAction(selectAll)

        action = self.strategy_table.popMenu.exec_(self.strategy_table.mapToGlobal(point))
        items = self.strategy_table.selectedItems()
        # strategy_id = self.strategy_table.item(row, 0).text()
        strategy_id_list = []
        for item in items:
            if self.strategy_table.indexFromItem(item).column() == 0:
                strategy_id_list.append(int(item.text()))
        if action == run:
            self._controller.resumeRequest(strategy_id_list)
        elif action == stop:
            self._controller.quitRequest(strategy_id_list)
        elif action == delete:
            self._controller.delStrategy(strategy_id_list)
        elif action == report:
            pass
        elif action == onSignal:
            self._controller.signalDisplay(strategy_id_list)
        elif action == policy:
            self._controller.paramSetting(strategy_id_list)
        elif action == selectAll:
            self.strategy_table.selectAll()
        else:
            pass

    def create_func_doc(self):
        self.func_doc = QWidget()
        self.func_doc_layout = QVBoxLayout()
        self.func_doc_layout.setSpacing(0)
        self.func_doc_layout.setContentsMargins(0, 5, 0, 0)
        self.func_doc_line = QLabel()
        self.func_doc_line.setText('函数简介')
        self.func_content = QTextBrowser()
        self.func_doc_layout.addWidget(self.func_doc_line)
        self.func_doc_layout.addWidget(self.func_content)
        self.func_doc.setLayout(self.func_doc_layout)

    def strategy_tree_clicked(self):
        # 策略双击槽函数
        index = self.strategy_tree.currentIndex()
        model = index.model()  # 请注意这里可以获得model的对象
        item_path = model.filePath(index)
        if not os.path.isdir(item_path):
            self.contentEdit.sendCustomSignal(item_path)
            self.strategy_path = item_path

    def func_tree_clicked(self):
        item = self.func_tree.currentItem()
        if item.parent():
            item_text = globals()['BaseApi'].__dict__.get(item.text(0), None).__doc__
            text = item_text.lstrip("\n") if item_text else ''
            self.func_content.setText(text.replace(' ', ''))
            self.func_doc_line.setText(item.text(0))

    def search_tree_clicked(self):
        item = self.search_tree.currentItem()
        item_text = globals()['BaseApi'].__dict__.get(item.text(0), None).__doc__
        text = item_text.lstrip("\n") if item_text else ''
        self.func_content.setText(text.replace(' ', ''))
        self.func_doc_line.setText(item.text(0))

    def search(self, word):
        self.search_tree.clear()
        # table数据
        func_list = []
        for k, v in _all_func_.items():
            for item in v:
                if word in item[0] or word in item[1]:
                    func_list.append(item)
        func_list.sort(key=lambda x: x[0])

        for v in func_list:
            root = QTreeWidgetItem(self.search_tree)
            root.setText(0, v[0])
            root.setText(1, v[1])

    def create_strategy_policy_win(self, param, path, flag):
        # 运行点击槽函数，弹出策略属性设置窗口
        if path:
            self.strategy_policy_win = StrategyPolicy(self._controller, path, param=param, flag=flag)

            # ----------------------解析g_params参数----------------------------
            g_params = parseStrategtParam(path)
            self.strategy_policy_win.paramsTableWidget.setRowCount(len(g_params))
            for i in range(len(self._userNo)):
                self.strategy_policy_win.userComboBox.addItem(self._userNo[i]['UserNo'])
                self.strategy_policy_win.userComboBox.setCurrentIndex(0)
            for i, item in enumerate(g_params.items()):
                param_type = ''
                if isinstance(item[1][0], str):
                    param_type = 'str'
                if isinstance(item[1][0], int):
                    param_type = 'int'
                if isinstance(item[1][0], float):
                    param_type = 'float'
                if isinstance(item[1][0], bool):
                    param_type = 'bool'
                self.strategy_policy_win.paramsTableWidget.setItem(i, 0, QTableWidgetItem(str(item[0])))
                self.strategy_policy_win.paramsTableWidget.setItem(i, 1, QTableWidgetItem(str(item[1][0])))
                self.strategy_policy_win.paramsTableWidget.setItem(i, 2, QTableWidgetItem(param_type))
                self.strategy_policy_win.paramsTableWidget.setItem(i, 3, QTableWidgetItem(str(item[1][1])))
            self.strategy_policy_win.contractWin.select.clicked.connect(
                lambda: self.strategy_policy_win.contractSelect(self._exchange, self._commodity, self._contract))
            self.strategy_policy_win.setWindowModality(Qt.ApplicationModal)  # 设置阻塞父窗口
            self.strategy_policy_win.show()
        else:
            QMessageBox.warning(self, '提示', '请选择策略！！！', QMessageBox.Yes)

    def save_strategy(self):
        if self.strategy_path:
            self.contentEdit.on_saveclick(self.strategy_path)
        else:
            QMessageBox.warning(self, '提示', '请选择策略！！！', QMessageBox.Yes)

    def updateLogText(self):
        guiQueue = self._controller.get_logger().getGuiQ()
        errData, usrData, sigData = "", "", ""
        flag = True
        try:
            while flag:
                logData = guiQueue.get_nowait()
                if logData[0] == "U":
                    usrData += logData[1] + "\n"
                elif logData[0] == "E":
                    errData += logData[1] + "\n"
                elif logData[0] == "S":
                    sigData += logData[1] + "\n"

                if guiQueue.empty():
                    flag = False
        except Exception as e:
            return
        else:
            if usrData:
                self.user_log_widget.append(usrData)
            if errData:
                self.error_info_widget.append(errData)
            if sigData:
                self.signal_log_widget.append(sigData)
        self.timer.start(1000)

    def setConnect(self, src):
        if src == 'Q':
            self.statusBar.setText("即时行情连接成功")
        if src == 'H':
            self.statusBar.setText("历史行情连接成功")

        if src == 'T':
            self.statusBar.setText("交易服务连接成功")

        if src == 'S':
            self.statusBar.setText("极星9.5连接成功")

    def setDisconnect(self, src):
        if src == 'Q':
            self.statusBar.setText("即时行情断连")
        if src == 'H':
            self.statusBar.setText("历史行情断连")

        if src == 'T':
            self.statusBar.setText("交易服务断连")

        if src == 'S':
            self.statusBar.setText("极星9.5退出")
            QMessageBox.critical("错误", "极星9.5退出")

    def addExecute(self, dataDict):
        values = self._formatMonitorInfo(dataDict)

        if not values:
            return

        strategyId = dataDict["StrategyId"]
        strategy_id_list = self.get_run_strategy_id()
        try:
            if strategyId in strategy_id_list:
                self.updateRunStage(strategyId, dataDict[5])
                return
        except Exception as e:
            self._logger.warn("addExecute exception")
        else:
            row = self.strategy_table.rowCount()
            self.strategy_table.setRowCount(row + 1)
            for j in range(len(values)):
                item = QTableWidgetItem(str(values[j]))
                item.setTextAlignment(Qt.AlignCenter)  # 设置文本居中显示
                self.strategy_table.setItem(row, j, item)

    def _formatMonitorInfo(self, dataDict):
        """
        格式化监控需要的信息
        :param dataDict: 策略的所有信息
        :return: 需要展示的信息
        """

        try:
            Id = dataDict['StrategyId']
            UserNo = dataDict["Config"]["Money"]["UserNo"]
            StName = dataDict['StrategyName']
            BenchCon = dataDict['ContractNo']
            kLineType = dataDict['KLineType']
            kLineSlice = dataDict['KLinceSlice']

            Frequency = str(kLineSlice) + kLineType

            # RunType     = "是" if dataDict['IsActualRun'] else "否"
            RunType = RunMode[dataDict["IsActualRun"]]
            Status = StrategyStatus[dataDict["StrategyState"]]
            InitFund = dataDict['InitialFund']

            Available = "{:.2f}".format(InitFund)
            MaxRetrace = 0.0
            TotalProfit = 0.0
            WinRate = 0.0

            return [
                Id,
                UserNo,
                StName,
                BenchCon,
                Frequency,
                Status,
                RunType,
                InitFund,
                Available,
                MaxRetrace,
                TotalProfit,
                WinRate
            ]

        except KeyError:
            traceback.print_exc()
            return []

    def get_run_strategy_id(self):
        strategy_id_list = []
        for i in range(self.strategy_table.rowCount()):
            strategy_id_list.append(int(self.strategy_table.item(i, 0).text()))
        return strategy_id_list

    def updateValue(self, strategyId, dataDict):
        """更新策略ID对应的运行数据"""

        colValues = {
            8: "{:.2f}".format(dataDict["Available"]),
            9: "{:.2f}".format(dataDict["MaxRetrace"]),
            10: "{:.2f}".format(dataDict["NetProfit"]),
            11: "{:.2f}".format(dataDict["WinRate"])
        }
        row = self.get_row_from_strategy_id(strategyId)
        if row != -1:
            for k, v in colValues.items():
                try:
                    item = QTableWidgetItem(v)
                    self.strategy_table.setItem(row, k, item)
                except Exception as e:
                    self._logger.error(f"[UI][{strategyId}]: 更新策略执行数据时出错，执行列表中该策略已删除！")

    def updateRunStage(self, strategyId, status):
        """更新策略运行阶段"""
        row = self.get_row_from_strategy_id(strategyId)
        if row != -1:
            item = QTableWidgetItem(str(StrategyStatus[status]))
            self.strategy_table.setItem(row, 5, item)

    def updateRunMode(self, strategyId, status):
        """更新策略运行模式"""
        row = self.get_row_from_strategy_id(strategyId)
        if row != -1:
            item = QTableWidgetItem(str(status))
            self.strategy_table.setItem(row, 6, item)

    def delUIStrategy(self, strategy_id):
        """
        删除监控列表中的策略
        :param strategyIdList: 待删除的策略列表
        :return:
        """
        row = self.get_row_from_strategy_id(strategy_id)
        if row != -1:
            self.strategy_table.removeRow(row)

    def get_row_from_strategy_id(self, strategy_id):
        for row in range(self.strategy_table.rowCount()):
            if int(self.strategy_table.item(row, 0).text()) == strategy_id:
                return row
        return -1

    def loadSysLogFile(self):
        """读取本地系统日志"""
        sysLogPath = r"./log/equant.log"
        # with open(sysLogPath, "r", encoding="utf-8") as f:
        with open(sysLogPath, "r") as f:
            data = f.read()
        self.sys_log_widget.setText(data)
        self.sys_log_widget.moveCursor(QTextCursor.End)

    def readPositionConfig(self):
        """读取配置文件"""
        if os.path.exists(r"./config/loadpositionon.json"):
            with open(r"./config/loadpositionon.json", "r", encoding="utf-8") as f:
                try:
                    result = json.loads(f.read())
                except json.decoder.JSONDecodeError:
                    return None
                else:
                    return result
        else:
            filePath = os.path.abspath(r"./config/loadpositionon.json")
            f = open(filePath, 'w')
            f.close()

    def writePositionConfig(self, configure):
        """写入配置文件"""
        # 将文件内容追加到配置文件中
        try:
            config = self.readConfig()
        except:
            config = None
        if config:
            for key in configure:
                config[key] = configure[key]
                break
        else:
            config = configure

        with open(r"./config/loadpositionon.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(config, indent=4))

    def change_connection(self):
        if self.intervalCheckBox.isChecked():
            self.spin.valueChanged.connect(self.save_position_config)
            self.cbComboBox.currentIndexChanged.connect(self.save_position_config)
            self.intervalSpinBox.valueChanged.connect(self.save_position_config)
            self.reducePositionCheckBox.stateChanged.connect(self.save_position_config)
        else:
            self.spin.valueChanged.disconnect(self.save_position_config)
            self.cbComboBox.currentIndexChanged.disconnect(self.save_position_config)
            self.intervalSpinBox.valueChanged.disconnect(self.save_position_config)
            self.reducePositionCheckBox.stateChanged.disconnect(self.save_position_config)

    def save_position_config(self, OneKeySync=False):
        config = {
            'OneKeySync': True if OneKeySync else False,  # 一键同步
            'AutoSyncPos': self.intervalCheckBox.isChecked(),  # 是否自动同步
            'PriceType': self.cbComboBox.currentIndex(),  # 价格类型 0:对盘价, 1:最新价, 2:市价
            'PriceTick': self.spin.value(),  # 超价点数
            'OnlyDec': self.reducePositionCheckBox.isChecked(),  # 是否只做减仓同步
            'SyncTick': self.intervalSpinBox.value(),  # 同步间隔，毫秒
        }
        print(config)
        self.writePositionConfig(config)
        self._controller._request.resetSyncPosConf(config)

    def valid_spin(self):
        if self.cbComboBox.currentIndex() == 2:
            self.spin.setEnabled(False)
        else:
            self.spin.setEnabled(True)

    def updateSyncPosition(self, positions):
        self.pos_table.clearContents()
        self.pos_table.setRowCount(len(positions))
        for i in range(len(positions)):
            positions[0][2] = int(time.time() - 1573265040)
            for j in range(len(positions[i])):
                item = QTableWidgetItem(str(positions[i][j]))
                self.pos_table.setItem(i, j, item)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    m = QSharedMemory(app.applicationName())
    if not m.create(1):
        QMessageBox.warning(None, '警告', '程序已经在运行！！！')
    else:
        quant = QuantApplication()
        quant.show()
        sys.exit(app.exec_())