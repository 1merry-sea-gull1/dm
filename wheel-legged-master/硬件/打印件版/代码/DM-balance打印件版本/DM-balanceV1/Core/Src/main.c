/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2024 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "cmsis_os.h"
#include "dma.h"
#include "fdcan.h"
#include "spi.h"
#include "tim.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "BMI088driver.h"
#include "kalman_filter.h"
#include "mahony_filter.h"
#include "bsp_dwt.h"
#include "BMI088Middleware.h"
#include "can_bsp.h"
#include "dm4310_drv.h"
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* 电机测试模式：1 开启，0 恢复完整轮腿固件 */
#define MOTOR_TEST_MODE       1

/* 1 表示六台同时测试，0 表示只测试 MOTOR_TEST_ID 指定的电机 */
#define MOTOR_TEST_ALL        1

/* 单电机模式下的电机编号：1~6 */
#define MOTOR_TEST_ID         0x04

/* 测试扭矩，单位N*m；仅在电机空载或整机可靠固定时使用 */
#define MOTOR_TEST_TORQUE     0.50f
#define MOTOR_TEST_MAX_TORQUE 0.50f

/* 每次输出扭矩持续500ms，然后归零等待1000ms，共执行3次 */
#define MOTOR_TEST_PULSE_MS   500U
#define MOTOR_TEST_PAUSE_MS   1000U
#define MOTOR_TEST_PULSES     3U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
void PeriphCommonClock_Config(void);
void MX_FREERTOS_Init(void);
/* USER CODE BEGIN PFP */
#if MOTOR_TEST_MODE
static void MotorTest_Run(void);
#endif
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */
//06 01 00 00 00 00 00 00 00 00 00 00 00 00 80 3F
  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

/* Configure the peripherals common clocks */
  PeriphCommonClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_SPI2_Init();
  MX_FDCAN1_Init();
  MX_FDCAN2_Init();
  MX_TIM3_Init();
  MX_FDCAN3_Init();
  /* USER CODE BEGIN 2 */
	DWT_Init(480);
  
    /* BMI088初始化 */
  while (BMI088_init(&hspi2, 0) != BMI088_NO_ERROR)
	{
	  ;
	}
	Power_OUT1_ON;//imu初始化完成，可控电源打开，led灯亮
	Power_OUT2_ON;
	
  FDCAN1_Config();//can过滤器初始化
	FDCAN2_Config();

#if MOTOR_TEST_MODE
  MotorTest_Run();
#endif
  /* USER CODE END 2 */

  /* Call init function for freertos objects (in freertos.c) */
  MX_FREERTOS_Init();

  /* Start scheduler */
  osKernelStart();

  /* We should never get here as control is now taken by the scheduler */
  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
 
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Supply configuration update enable
  */
  HAL_PWREx_ConfigSupply(PWR_LDO_SUPPLY);

  /** Configure the main internal regulator output voltage
  */
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE0);

  while(!__HAL_PWR_GET_FLAG(PWR_FLAG_VOSRDY)) {}

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 2;
  RCC_OscInitStruct.PLL.PLLN = 40;
  RCC_OscInitStruct.PLL.PLLP = 1;
  RCC_OscInitStruct.PLL.PLLQ = 2;
  RCC_OscInitStruct.PLL.PLLR = 2;
  RCC_OscInitStruct.PLL.PLLRGE = RCC_PLL1VCIRANGE_3;
  RCC_OscInitStruct.PLL.PLLVCOSEL = RCC_PLL1VCOWIDE;
  RCC_OscInitStruct.PLL.PLLFRACN = 0;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2
                              |RCC_CLOCKTYPE_D3PCLK1|RCC_CLOCKTYPE_D1PCLK1;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.SYSCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB3CLKDivider = RCC_APB3_DIV2;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_APB1_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_APB2_DIV2;
  RCC_ClkInitStruct.APB4CLKDivider = RCC_APB4_DIV2;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_3) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief Peripherals Common Clock Configuration
  * @retval None
  */
void PeriphCommonClock_Config(void)
{
  RCC_PeriphCLKInitTypeDef PeriphClkInitStruct = {0};

  /** Initializes the peripherals clock
  */
  PeriphClkInitStruct.PeriphClockSelection = RCC_PERIPHCLK_FDCAN;
  PeriphClkInitStruct.PLL2.PLL2M = 24;
  PeriphClkInitStruct.PLL2.PLL2N = 200;
  PeriphClkInitStruct.PLL2.PLL2P = 2;
  PeriphClkInitStruct.PLL2.PLL2Q = 2;
  PeriphClkInitStruct.PLL2.PLL2R = 2;
  PeriphClkInitStruct.PLL2.PLL2RGE = RCC_PLL2VCIRANGE_0;
  PeriphClkInitStruct.PLL2.PLL2VCOSEL = RCC_PLL2VCOMEDIUM;
  PeriphClkInitStruct.PLL2.PLL2FRACN = 0;
  PeriphClkInitStruct.FdcanClockSelection = RCC_FDCANCLKSOURCE_PLL2;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInitStruct) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

#if MOTOR_TEST_MODE
static void MotorTest_Run(void)
{
  const uint16_t all_motor_ids[6] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06};
  uint16_t test_ids[6];
  uint8_t motor_count;
  hcan_t *hcan;
  float target_torque = MOTOR_TEST_TORQUE;
  uint32_t pulse;
  uint32_t elapsed;
  uint8_t i;
  uint8_t m;

#if MOTOR_TEST_ALL
  motor_count = 6U;
  for (i = 0U; i < motor_count; i++)
  {
    test_ids[i] = all_motor_ids[i];
  }
#else
  if ((MOTOR_TEST_ID < 0x01U) || (MOTOR_TEST_ID > 0x06U))
  {
    Error_Handler();
    return;
  }

  motor_count = 1U;
  test_ids[0] = MOTOR_TEST_ID;
#endif

  if (target_torque > MOTOR_TEST_MAX_TORQUE)
  {
    target_torque = MOTOR_TEST_MAX_TORQUE;
  }
  else if (target_torque < -MOTOR_TEST_MAX_TORQUE)
  {
    target_torque = -MOTOR_TEST_MAX_TORQUE;
  }

  HAL_Delay(100U);

  /* 使能当前选择的一台或六台电机，1~3号使用CAN1，4~6号使用CAN2 */
  for (i = 0U; i < 10U; i++)
  {
    for (m = 0U; m < motor_count; m++)
    {
      hcan = (test_ids[m] <= 0x03U) ? &hfdcan1 : &hfdcan2;
      enable_motor_mode(hcan, test_ids[m], MIT_MODE);
    }
    HAL_Delay(1U);
  }

  /* 先保持零扭矩，确认使能帧和控制帧连续发送 */
  for (i = 0U; i < 20U; i++)
  {
    for (m = 0U; m < motor_count; m++)
    {
      hcan = (test_ids[m] <= 0x03U) ? &hfdcan1 : &hfdcan2;
      mit_ctrl(hcan, test_ids[m], 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
    }
    HAL_Delay(10U);
  }

  for (pulse = 0U; pulse < MOTOR_TEST_PULSES; pulse++)
  {
    for (elapsed = 0U; elapsed < MOTOR_TEST_PULSE_MS; elapsed += 10U)
    {
      for (m = 0U; m < motor_count; m++)
      {
        hcan = (test_ids[m] <= 0x03U) ? &hfdcan1 : &hfdcan2;
        mit_ctrl(hcan, test_ids[m], 0.0f, 0.0f, 0.0f, 0.0f, target_torque);
      }
      HAL_Delay(10U);
    }

    for (elapsed = 0U; elapsed < MOTOR_TEST_PAUSE_MS; elapsed += 10U)
    {
      for (m = 0U; m < motor_count; m++)
      {
        hcan = (test_ids[m] <= 0x03U) ? &hfdcan1 : &hfdcan2;
        mit_ctrl(hcan, test_ids[m], 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
      }
      HAL_Delay(10U);
    }
  }

  /* 测试结束，全部归零并失能，不进入轮腿控制任务 */
  for (i = 0U; i < 20U; i++)
  {
    for (m = 0U; m < motor_count; m++)
    {
      hcan = (test_ids[m] <= 0x03U) ? &hfdcan1 : &hfdcan2;
      mit_ctrl(hcan, test_ids[m], 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
    }
    HAL_Delay(10U);
  }

  for (i = 0U; i < 10U; i++)
  {
    for (m = 0U; m < motor_count; m++)
    {
      hcan = (test_ids[m] <= 0x03U) ? &hfdcan1 : &hfdcan2;
      disable_motor_mode(hcan, test_ids[m], MIT_MODE);
    }
    HAL_Delay(1U);
  }

  while (1)
  {
    HAL_Delay(1000U);
  }
}
#endif

/* USER CODE END 4 */

/**
  * @brief  Period elapsed callback in non blocking mode
  * @note   This function is called  when TIM2 interrupt took place, inside
  * HAL_TIM_IRQHandler(). It makes a direct call to HAL_IncTick() to increment
  * a global variable "uwTick" used as application time base.
  * @param  htim : TIM handle
  * @retval None
  */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
  /* USER CODE BEGIN Callback 0 */

  /* USER CODE END Callback 0 */
  if (htim->Instance == TIM2) {
    HAL_IncTick();
  }
  /* USER CODE BEGIN Callback 1 */

  /* USER CODE END Callback 1 */
}

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
